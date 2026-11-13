"""saspy engine with selectable connection profiles (issue #6).

Implements the run protocol (spec §6.1), dataset upload conversion (§7), result
collection (§8) and run status (§6.5) against live SAS 9.4 / Viya via saspy.
Connection profiles are chosen per app or session; credentials come only from
``~/.authinfo`` or environment variables, never from the contract.

Live verification is recorded in the live SAS check reports (issue #11).
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import uuid
from collections.abc import Callable
from contextlib import suppress
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from ..collect import (
    CSV_MAX_ROWS,
    build_table,
    choices_code,
    csv_bytes,
    download_value,
    extract_plots,
    formatted_table_code,
    join_remote,
    scope_log,
    select_columns,
    split_member,
    table_meta_code,
    xlsx_bytes,
    xpt_bytes,
)
from ..contract import Contract
from ..recording import contract_sha256, key_for, program_sha256, save_recording
from ..result import Result
from ..upload import UploadError, read_upload, resolve_upload
from ..values import render_values
from ..wrapper import reset_code, wrapper_code
from .base import Engine

__all__ = ["SaspyEngine", "authinfo_path", "connect", "load_profiles", "preflight"]

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# syscc threshold above which a run is an error (spec §6.5).
SYSCC_ERROR = 4
# Submitted once per new SAS session (spec §6.1).
SESSION_SETUP_CODE = "/* SAShiny 1 session */\noptions notes;\n"

# ODA hosts by region (spec/tools/live_sas_check.py).
ODA_HOSTS = {
    "us1": ["odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"],
    "us2": ["odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"],
    "eu1": ["odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"],
    "ap1": ["odaws01-apse1.oda.sas.com", "odaws02-apse1.oda.sas.com"],
    "ap2": ["odaws01-apse1-2.oda.sas.com", "odaws02-apse1-2.oda.sas.com"],
}


def connect(  # noqa: PLR0913 - explicit connection parameters per backend
    profile: str,
    *,
    region: str = "us1",
    url: str | None = None,
    context: str | None = None,
    verify: bool = True,
    host: str | None = None,
    port: int = 8591,
    saspath: str | None = None,
    ssh_user: str | None = None,
    java: str | None = None,
    record_to: str | Path | None = None,
) -> SaspyEngine:
    """Build a SAS engine for one of three connection types.

    The consumer chooses the backend explicitly and supplies its connection
    details. SAShiny does not auto-detect or validate the SAS version: the
    responsibility for pointing at the correct endpoint/version rests with the
    caller. Credentials are never passed here — they come from ``~/.authinfo``
    keyed by the profile's ``authkey``.

    Args:
        profile: One of ``"oda"``, ``"viya"`` or ``"sas94"``. Required; there is
            no default.
        region: ODA region (``us1``/``us2``/``eu1``/``ap1``/``ap2``). Defaults
            to ``us1``.
        url: Viya base URL (required for ``viya``).
        context: Viya compute context name (optional).
        verify: Viya TLS verification (default ``True``).
        host: SAS 9.4 host (required for ``sas94``).
        port: SAS 9.4 IOM port (default ``8591``).
        saspath: SAS 9.4 executable path for SSH (optional; when given, SSH is
            used instead of IOM).
        ssh_user: SSH login user (optional).
        java: Path to the Java executable for IOM (optional; auto-detected when
            omitted).
        record_to: Directory where every run is also saved as a recording
            (spec §8.3) for offline replay with :class:`sashiny.MockEngine`.

    Returns:
        A :class:`SaspyEngine` configured for the chosen backend.

    Raises:
        ValueError: If ``profile`` is unknown or a required parameter is missing.

    """
    if profile == "oda":
        if region not in ODA_HOSTS:
            raise ValueError(f"unknown ODA region {region!r}; expected one of {sorted(ODA_HOSTS)}")
        cfg: dict[str, Any] = {
            "java": java or _find_java(),
            "iomhost": ODA_HOSTS[region],
            "iomport": 8591,
            "authkey": "oda",
            "encoding": "utf-8",
        }
    elif profile == "viya":
        if not url:
            raise ValueError("url is required for profile 'viya'")
        cfg = {"url": url, "authkey": "viya", "options": ["fullstimer"]}
        if context:
            cfg["context"] = context
        if not verify:
            cfg["verify"] = False
    elif profile == "sas94":
        if not host:
            raise ValueError("host is required for profile 'sas94'")
        if saspath:
            cfg = {
                "saspath": saspath,
                "ssh": _find_ssh(),
                "host": host,
                "encoding": "utf-8",
                "options": ["-fullstimer"],
            }
            if ssh_user:
                cfg["luser"] = ssh_user
        else:
            cfg = {
                "java": java or _find_java(),
                "iomhost": host,
                "iomport": port,
                "authkey": "iom",
                "encoding": "utf-8",
            }
    else:
        raise ValueError(f"unknown profile {profile!r}; expected 'oda', 'viya' or 'sas94'")

    return SaspyEngine(cfg, record_to=record_to)


def _find_java() -> str | None:
    """Locate the Java executable, or ``None`` when not found."""
    import shutil  # noqa: PLC0415

    if os.environ.get("JAVA_HOME"):
        cand = Path(os.environ["JAVA_HOME"]) / "bin" / ("java.exe" if os.name == "nt" else "java")
        if cand.exists():
            return str(cand)
    return shutil.which("java")


def _find_ssh() -> str:
    """Locate the SSH executable."""
    import shutil  # noqa: PLC0415

    return shutil.which("ssh") or "/usr/bin/ssh"


def load_profiles(path: str | Path | None = None) -> dict[str, Any]:
    """Load connection profiles from a YAML file.

    Args:
        path: Path to the connections file. Defaults to ``SASHINY_CONNECTIONS``
            or ``~/.config/sashiny/connections.yml``.

    Returns:
        The parsed profiles mapping (``default`` + ``profiles``).

    """
    import yaml  # noqa: PLC0415 - optional dependency

    if path is None:
        import os  # noqa: PLC0415

        path = os.environ.get("SASHINY_CONNECTIONS") or str(
            Path.home() / ".config" / "sashiny" / "connections.yml"
        )
    p = Path(path)
    if not p.is_file():
        return {"default": "offline", "profiles": {}}
    data: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data


def classify_log(log: str) -> dict[str, int]:
    """Count ERROR/WARNING lines in a log (spec §6.5)."""
    counts = {"error": 0, "warning": 0}
    for line in log.splitlines():
        if line.startswith("ERROR"):
            counts["error"] += 1
        elif line.startswith("WARNING"):
            counts["warning"] += 1
    return counts


def run_status(log: str, run_id: str = "fixture") -> tuple[str, int | None]:
    """Determine run status from the log (spec §6.5)."""
    m = re.search(rf"SASHINY-END run={re.escape(run_id)} syscc=(\d+)", log)
    if not m:
        return "error", None
    syscc = int(m.group(1))
    counts = classify_log(log)
    if syscc > SYSCC_ERROR or counts["error"]:
        return "error", syscc
    if syscc == SYSCC_ERROR or counts["warning"]:
        return "warning", syscc
    return "success", syscc


_PATH_LINE = re.compile(r"^SASHINY-PATH=(.*?)\s*$", re.MULTILINE)
_DATETIME_FORMATS = (
    "DATETIME",
    "DTDATE",
    "E8601DT",
    "B8601DT",
    "IS8601DT",
    "NLDATM",
    "MDYAMPM",
    "DTWKDATX",
)
_TIME_FORMATS = ("TIME", "HHMM", "E8601TM", "B8601TM", "TOD", "NLTIME")
_SAS_EPOCH = datetime(1960, 1, 1)
_SECONDS_PER_DAY = 86400


def _sas_number(value: Any, fmt: str) -> Any:
    """Turn values saspy converted to Python dates back into SAS numbers (§8.1)."""
    stamp = getattr(value, "to_pydatetime", None)
    if stamp is not None and not hasattr(value, "total_seconds"):
        value = stamp()
    if isinstance(value, datetime):
        upper = fmt.upper()
        naive = value.replace(tzinfo=None)
        if upper.startswith(_TIME_FORMATS):
            return naive.hour * 3600 + naive.minute * 60 + naive.second + naive.microsecond / 1e6
        seconds = (naive - _SAS_EPOCH).total_seconds()
        return seconds if upper.startswith(_DATETIME_FORMATS) else seconds / _SECONDS_PER_DAY
    if isinstance(value, date):
        return (value - _SAS_EPOCH.date()).days
    total = getattr(value, "total_seconds", None)
    if total is not None:
        return total()
    return value


def _is_missing(value: Any) -> bool:
    try:
        import pandas as pd  # noqa: PLC0415 - optional dependency

        return bool(pd.isna(value))
    except (ImportError, TypeError, ValueError):
        return value is None


def _choice_text(value: Any) -> str:
    """Render a choice cell as text (integers without a trailing ``.0``)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _write_cfgfile(cfg: dict[str, Any], cfgname: str, folder: Path) -> Path:
    """Write a saspy configuration module that defines ``cfgname`` from ``cfg``."""
    if not cfgname.isidentifier():
        raise ValueError(f"cfgname must be a Python identifier: {cfgname!r}")
    path = folder / f"sascfg_{cfgname}.py"
    path.write_text(
        "# Generated by SAShiny; do not edit.\n"
        f"SAS_config_names = [{cfgname!r}]\n"
        f"{cfgname} = {cfg!r}\n",
        encoding="utf-8",
    )
    return path


def authinfo_path() -> Path:
    """Return the saspy credentials file path.

    This is ``~/.authinfo``, or ``_authinfo`` in ``USERPROFILE`` on Windows.
    """
    if os.name == "nt":
        return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "_authinfo"
    return Path.home() / ".authinfo"


def preflight(cfg: dict[str, Any]) -> None:
    """Fail fast, with a clear message, on settings saspy would reject or prompt for.

    saspy prompts for a user id and password on stdin when the ``authkey`` is
    missing from the authinfo file, which would hang a Shiny app; and it reports
    a missing Java as an invalid configuration.

    Raises:
        RuntimeError: Java is missing for an IOM connection, or the ``authkey``
            has no entry in the authinfo file.

    """
    if "iomhost" in cfg and not cfg.get("java"):
        raise RuntimeError(
            "Java was not found; IOM connections (ODA, SAS 9.4) need Java 8 or later. "
            "Install it, set JAVA_HOME, or pass java='/path/to/java'."
        )
    key = cfg.get("authkey")
    if key:
        path = authinfo_path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        if not any(line.split()[:1] == [key] for line in lines):
            raise RuntimeError(
                f"no credentials for '{key}' in {path}. Add a line: "
                f"{key} user <user id> password <password>"
            )


class SaspyEngine(Engine):
    """A live SAS engine backed by saspy.

    One engine holds one SAS session, started on first use and reused across
    runs (each run resets WORK, spec §6.2). Use :class:`sashiny.SessionPool` to
    serve several users.

    Args:
        cfg: A saspy configuration dict (written to a temporary ``sascfg``
            module) or the path of an existing saspy configuration file.
        cfgname: The configuration name inside that file.
        record_to: When set, every completed run is also written as a
            recording (§8.3) in this directory, for offline replay.
        session_factory: Advanced/testing hook returning a saspy-like session
            object (``submit``, ``sd2df``, ``df2sd``, ``download``, ``endsas``).

    """

    name = "saspy"
    version = "0.1.0"

    def __init__(
        self,
        cfg: dict[str, Any] | str | Path,
        cfgname: str = "sashiny",
        *,
        record_to: str | Path | None = None,
        session_factory: Callable[[], Any] | None = None,
    ) -> None:
        """Create a saspy engine; the SAS session starts on the first run."""
        self.cfg = cfg
        self.cfgname = cfgname
        self.record_to = Path(record_to) if record_to else None
        self._factory = session_factory
        self._sas: Any = None
        self._sas_version_text: str | None = None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._choices: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._cancelled = False

    # ------------------------------------------------------------------ session

    def _session(self) -> Any:
        if self._cancelled:
            raise RuntimeError("run was cancelled (timeout)")
        if self._sas is None:
            if self._factory is not None:
                self._sas = self._factory()
            else:
                if isinstance(self.cfg, dict):
                    preflight(self.cfg)
                import saspy  # noqa: PLC0415 - optional dependency

                if isinstance(self.cfg, dict):
                    self._tmp = tempfile.TemporaryDirectory(prefix="sashiny-cfg-")
                    cfgfile = str(_write_cfgfile(self.cfg, self.cfgname, Path(self._tmp.name)))
                else:
                    cfgfile = str(self.cfg)
                self._sas = saspy.SASsession(cfgfile=cfgfile, cfgname=self.cfgname, results="HTML")
            # Session setup (spec 6.1): ODA starts with NONOTES, which hides the sentinels.
            self._sas.submit(SESSION_SETUP_CODE, results="TEXT")
        return self._sas

    def _submit(self, code: str, results: str = "TEXT") -> dict[str, str]:
        res: dict[str, str] = self._session().submit(code, results=results)
        return res

    def _sas_version(self) -> str:
        if self._sas_version_text is None:
            try:
                log = self._submit("%put SXVER=&sysvlong;")["LOG"]
                # Anchor at line start: the source echo also contains "SXVER=".
                m = re.search(r"^SXVER=(\S+)", log, re.MULTILINE)
                self._sas_version_text = m.group(1) if m else ""
            except Exception:
                self._sas_version_text = ""
        return self._sas_version_text

    def close(self) -> None:
        """Close the SAS session and remove the temporary configuration."""
        self._choices.clear()
        self._sas_version_text = None
        if self._sas is not None:
            try:
                self._sas.endsas()
            finally:
                self._sas = None
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def _discard_session(self) -> None:
        """Close the current session (if any) and forget it.

        Used when a run fails or times out: the session must be ended before the
        reference is lost, otherwise it leaks (spec §6.5).
        """
        sas = self._sas
        self._sas = None
        if sas is not None:
            with suppress(Exception):
                sas.endsas()

    def choices(self, contract: Contract) -> dict[str, list[dict[str, str]]]:
        """Read ``choices_from`` choices once per session and contract (spec §6.4)."""
        out: dict[str, list[dict[str, str]]] = {}
        tag = contract_sha256(contract) or str(contract.base_dir)
        for iid, spec in (contract.data.get("inputs") or {}).items():
            source = spec.get("choices_from")
            if source is None:
                continue
            if (tag, iid) not in self._choices:
                self._choices[(tag, iid)] = self._read_choices(source)
            out[iid] = self._choices[(tag, iid)]
        return out

    def _read_choices(self, source: dict[str, Any]) -> list[dict[str, str]]:
        value = source["value_column"]
        label = source.get("label_column")
        try:
            self._submit(choices_code(source))
            df = self._session().sd2df("_sx_choices", "work")
            if df is None:
                raise ValueError(f"could not read choices from {source['dataset']}")
            lookup = {str(c).upper(): c for c in df.columns}
            values = [_choice_text(v) for v in df[lookup[value.upper()]]]
            labels = (
                values if label is None else [_choice_text(v) for v in df[lookup[label.upper()]]]
            )
            return [{"value": v, "label": lab or v} for v, lab in zip(values, labels, strict=True)]
        finally:
            self._submit("proc datasets library=work nolist nowarn; delete _sx_choices; quit;")

    # ------------------------------------------------------------------ run

    def run(  # noqa: D102 - documented on the base class
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Result:
        today = today or date.today()
        run_id = run_id or str(uuid.uuid4())
        started = datetime.now(timezone.utc)
        timeout = float((contract.data.get("run") or {}).get("timeout_seconds", 300))

        # The SAS work blocks (saspy submit), so run it in a worker thread and
        # enforce the whole-run deadline (spec §2.3, §6.5). On timeout the session
        # is aborted and the pool discards it.
        box: dict[str, Result] = {}
        self._cancelled = False

        def work() -> None:
            try:
                box["result"] = self._run(contract, values, today, uploads, run_id, started)
            except Exception as exc:  # reported on the result, never raised
                failed = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
                failed.metadata["engine_error"] = f"{type(exc).__name__}: {exc}"
                box["result"] = failed

        thread = threading.Thread(target=work, name=f"sashiny-run-{run_id}", daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            self._cancelled = True
            self._discard_session()
            result = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
            result.metadata["engine_error"] = f"run exceeded timeout_seconds={timeout:g}"
            return result
        return box["result"]

    def _run(  # noqa: PLR0913, PLR0917 - the run protocol is inherently long
        self,
        contract: Contract,
        values: dict[str, Any],
        today: date,
        uploads: dict[str, Any] | None,
        run_id: str,
        started: datetime,
    ) -> Result:
        data = contract.data
        flags = {k: bool(v) for k, v in (uploads or {}).items()}
        try:
            override = {k: [c["value"] for c in v] for k, v in self.choices(contract).items()}
        except Exception as exc:  # reported on the result, never raised
            failed = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
            failed.metadata["engine_error"] = f"{type(exc).__name__}: {exc}"
            self._discard_session()
            return failed
        macros, issues = render_values(
            data, values, today, choices_override=override or None, uploads=flags
        )
        base: dict[str, Any] = {
            "contract_sha256": contract_sha256(contract),
            "program_sha256": program_sha256(contract),
            "macros": macros,
            "engine": self.name,
            "engine_version": self.version,
            "started_at": started,
        }
        if issues:
            result = Result.new(run_id, "error", **base)
            result.metadata["issues"] = [{"code": i.code, "input": i.path} for i in issues]
            return result

        try:
            files = self._prepare(contract, uploads)
            res = self._submit(
                wrapper_code(data, macros, self._program(contract), run_id=run_id), "HTML"
            )
        except UploadError as exc:
            result = Result.new(run_id, "error", **base)
            result.metadata["issues"] = [{"code": "V014", "message": str(exc)}]
            return result
        except Exception as exc:
            result = Result.new(run_id, "error", **base)
            result.metadata["engine_error"] = f"{type(exc).__name__}: {exc}"
            self._discard_session()  # the next run starts a fresh session
            return result

        log = res.get("LOG", "")
        status, syscc = run_status(log, run_id)
        result = Result.new(run_id, status, **base, sas_version=self._sas_version())
        result.log = log
        result.outputs, errors = self._collect(data, res)
        result.metadata["collect_errors"] = errors
        result.metadata["syscc"] = syscc
        ended = datetime.now(timezone.utc)
        result.metadata["ended_at"] = ended.isoformat()
        result.metadata["seconds"] = round((ended - started).total_seconds(), 2)
        if self.record_to is not None:
            try:
                path = save_recording(self.record_to, key_for(contract, macros, files), result)
                result.metadata["recording"] = str(path)
            except Exception as exc:  # a recording failure never discards a run
                result.metadata["recording_error"] = f"{type(exc).__name__}: {exc}"
        return result

    @staticmethod
    def _program(contract: Contract) -> bytes:
        return Path(contract.base_dir, str(contract.data["program"])).read_bytes()

    def _prepare(self, contract: Contract, uploads: dict[str, Any] | None) -> dict[str, Path]:
        """Reset the session (§6.2) and upload dataset inputs (§7)."""
        data = contract.data
        if (data.get("run") or {}).get("reset_work", True):
            self._submit(reset_code(data))
        files: dict[str, Path] = {}
        for iid, spec in (data.get("inputs") or {}).items():
            if spec["type"] != "dataset":
                continue
            upload = resolve_upload((uploads or {}).get(iid), spec, contract.base_dir)
            if upload is None:
                continue
            df, datetimes = read_upload(upload, spec)
            lib, mem = spec["target"].split(".", 1)
            self._session().df2sd(df, table=mem, libref=lib, datetimes=datetimes)
            files[iid] = upload.path
        return files

    # ------------------------------------------------------------------ collection

    def _collect(
        self, data: dict[str, Any], res: dict[str, str]
    ) -> tuple[dict[str, Any], list[str]]:
        """Collect every output per §8.2; a failure affects only that output."""
        outputs: dict[str, Any] = {}
        errors: list[str] = []
        html = res.get("LST", "")
        for oid, spec in (data.get("outputs") or {}).items():
            try:
                outputs[oid] = self._collect_one(oid, spec, html, res.get("LOG", ""))
            except Exception as exc:
                message = f"{oid}: {exc}"
                outputs[oid] = {"error": str(exc)}
                errors.append(message)
        return outputs, errors

    def _collect_one(self, oid: str, spec: dict[str, Any], html: str, log: str) -> Any:
        kind = spec["type"]
        if kind == "table":
            return self._table(
                spec["from"],
                spec.get("columns"),
                int(spec.get("max_rows", 10000)),
                formatted=bool(spec.get("formatted", False)),
            )
        if kind == "chart":
            return self._table(
                spec["from"],
                spec.get("columns"),
                int(spec.get("max_rows", 10000)),
                formatted=False,
            )
        if kind == "plot":
            return extract_plots(html, spec.get("select"))
        if kind == "html":
            return html
        if kind == "log":
            return scope_log(log, spec.get("scope", "program"))
        if kind == "download":
            return self._download(oid, spec)
        raise ValueError(f"unknown output type {kind}")

    def _table(
        self, ref: str, columns: list[str] | None, max_rows: int, *, formatted: bool
    ) -> dict[str, Any]:
        lib, mem = split_member(ref)
        sas = self._session()
        try:
            self._submit(table_meta_code(lib, mem))
            cols = sas.sd2df("_sx_cols", "work")
            if cols is None or len(cols) == 0:
                raise ValueError(f"dataset {lib}.{mem} not found")
            nobs = sas.sd2df("_sx_nobs", "work")
            total = None
            if nobs is not None and len(nobs) and not _is_missing(nobs.iloc[0, 0]):
                total = int(nobs.iloc[0, 0])
            meta = [
                {
                    "name": str(r["name"]).strip(),
                    "type": "numeric" if str(r["type"]).strip().lower() == "num" else "character",
                    "label": "" if _is_missing(r["label"]) else str(r["label"]).strip(),
                    "format": "" if _is_missing(r["format"]) else str(r["format"]).strip(),
                }
                for _, r in cols.iterrows()
            ]
            chosen = select_columns(meta, columns)
            names = [m["name"] for m in chosen]
            if formatted:
                self._submit(formatted_table_code(lib, mem, names, max_rows))
                df = sas.sd2df("_sx_fmt", "work")
                keys = [f"_sx_c{i}" for i in range(1, len(names) + 1)]
            else:
                df = sas.sd2df(mem, lib, dsopts={"obs": max_rows, "keep": " ".join(names)})
                keys = names
            if df is None:
                raise ValueError(f"could not read {lib}.{mem}")
            lookup = {str(c).upper(): c for c in df.columns}
            frame = df[[lookup[k.upper()] for k in keys]]
            rows = []
            for row in frame.itertuples(index=False, name=None):
                cells = []
                for value, m in zip(row, chosen, strict=True):
                    if formatted or m["type"] != "numeric":
                        cells.append(None if _is_missing(value) else value)
                    else:
                        cells.append(
                            None if _is_missing(value) else _sas_number(value, m["format"])
                        )
                rows.append(cells)
            return build_table(
                chosen, rows, total_rows=total, max_rows=max_rows, formatted=formatted
            )
        finally:
            self._submit("proc datasets library=work nolist nowarn; delete _sx_:; quit;")

    def _remote_dir(self, libref: str) -> str:
        log = self._submit(f"%put SASHINY-PATH=%sysfunc(pathname({libref}));")["LOG"]
        m = _PATH_LINE.search(log)
        if not m or not m.group(1):
            raise ValueError(f"cannot resolve the path of library {libref}")
        return m.group(1)

    def _fetch_file(self, remote: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="sashiny-dl-") as tmp:
            local = Path(tmp) / Path(remote.replace("\\", "/")).name
            res = self._session().download(str(local), remote)
            if isinstance(res, dict) and not res.get("Success", False):
                raise ValueError(f"download failed for {remote}")
            if not local.is_file():
                raise ValueError(f"download produced no file for {remote}")
            payload: bytes = local.read_bytes()
            return payload

    def _download(self, oid: str, spec: dict[str, Any]) -> dict[str, str]:
        fmt = spec["format"]
        name = spec.get("filename") or oid
        if fmt in ("rtf", "pdf"):
            remote = join_remote(self._remote_dir("work"), f"sashiny_{oid}.{fmt}")
            return download_value(name, fmt, self._fetch_file(remote))
        lib, mem = split_member(spec["from"])
        if fmt == "sas7bdat":
            remote = join_remote(self._remote_dir(lib), f"{mem.lower()}.sas7bdat")
            return download_value(name, fmt, self._fetch_file(remote))
        table = self._table(spec["from"], None, CSV_MAX_ROWS, formatted=False)
        if fmt == "csv":
            payload = csv_bytes(table)
        elif fmt == "xlsx":
            payload = xlsx_bytes(table, mem)
        elif fmt == "xpt":
            payload = xpt_bytes(table, mem)
        else:
            raise ValueError(f"unsupported download format {fmt}")
        return download_value(name, fmt, payload)
