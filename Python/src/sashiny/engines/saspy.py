"""saspy engine for live SAS 9.4, SAS Viya and SAS OnDemand for Academics.

Implements the run protocol (spec §6.1), dataset upload conversion (§7), result
collection (§8) and run status (§6.5) via saspy. Only the three backends of spec
§6.6 are accepted, and a run needs the user's licence acknowledgement.
Credentials come only from ``~/.authinfo`` or environment variables, never from
the contract or function arguments.

Live verification is recorded in the live SAS check reports (issue #11).
"""

from __future__ import annotations

import os
import re
import tempfile
import threading
import uuid
import warnings
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .. import __version__
from ..collect import (
    CSV_MAX_ROWS,
    build_table,
    choices_code,
    csv_bytes,
    download_value,
    extract_plots,
    formatted_table_code,
    is_paired,
    join_remote,
    paired_parts,
    scope_log,
    select_columns,
    split_member,
    table_meta_code,
    xlsx_bytes,
    xpt_bytes,
)
from ..contract import Contract
from ..errors import EngineError, LicenseError, SashinyError
from ..recording import contract_sha256, program_sha256
from ..result import Result, utc_timestamp
from ..upload import UploadError, read_upload, resolve_upload, upload_supplied
from ..values import render_values
from ..wrapper import reset_code, wrapper_code
from .base import Engine

_MAX_PORT = 65535


class EngineValueError(EngineError, ValueError):
    """A saspy configuration or collection problem (an :class:`EngineError`)."""


class EngineRuntimeError(SashinyError, RuntimeError):
    """A saspy session or run problem (a :class:`SashinyError`)."""


__all__ = [
    "LICENSE_MESSAGE",
    "Backend",
    "SaspyEngine",
    "authinfo_path",
    "backend_of",
    "connect",
    "license_acknowledged",
    "load_profiles",
    "oda",
    "preflight",
    "sas94_iom",
    "sas94_ssh",
    "viya",
]

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# syscc threshold above which a run is an error (spec §6.5).
SYSCC_ERROR = 4
# Submitted once per new SAS session (spec §6.1).
SESSION_SETUP_CODE = "/* SAShiny 1 session */\noptions notes;\n"

LICENSE_MESSAGE = (
    "SAS licence not acknowledged: SAShiny runs programs only on a SAS system you are "
    "licensed to use. Confirm this with license_ack=True or the environment variable "
    "SASHINY_LICENSE_ACK=true."
)
_SUPPORTED = "supported backends are SAS 9.4 (IOM or SSH), SAS Viya and SAS OnDemand for Academics"

# ODA hosts by region (spec/tools/live_sas_check.py).
ODA_HOSTS = {
    "us1": ["odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"],
    "us2": ["odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"],
    "eu1": ["odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"],
    "ap1": ["odaws01-apse1.oda.sas.com", "odaws02-apse1.oda.sas.com"],
    "ap2": ["odaws01-apse1-2.oda.sas.com", "odaws02-apse1-2.oda.sas.com"],
}


@dataclass(frozen=True)
class Backend:
    """A SAS backend for :func:`connect` (spec §6.6): its kind and saspy configuration."""

    kind: str
    cfg: dict[str, Any] = field(compare=False)
    detail: str = ""

    def __repr__(self) -> str:
        """Show the kind and its main detail (region, URL or host)."""
        return f"<sashiny backend> {self.kind}" + (f" ({self.detail})" if self.detail else "")


def oda(region: str = "us1", *, java: str | None = None) -> Backend:
    """SAS OnDemand for Academics over IOM (needs Java).

    Args:
        region: ``us1``, ``us2``, ``eu1``, ``ap1`` or ``ap2``.
        java: Path to the Java executable (optional; auto-detected).

    Returns:
        A :class:`Backend` for :func:`connect`.

    Raises:
        EngineValueError: For an unknown region.

    """
    if region not in ODA_HOSTS:
        raise EngineValueError(
            f"unknown ODA region {region!r}; expected one of {sorted(ODA_HOSTS)}"
        )
    cfg = {
        "java": java or _find_java(),
        "iomhost": ODA_HOSTS[region],
        "iomport": 8591,
        "authkey": "oda",
        "encoding": "utf-8",
    }
    return Backend("oda", cfg, region)


def viya(url: str, *, context: str | None = None, verify: bool = True) -> Backend:
    """SAS Viya over HTTP(S).

    Args:
        url: The Viya base URL, starting with ``https://`` or ``http://``.
        context: The compute context name (optional).
        verify: Verify TLS certificates (default ``True``).

    Returns:
        A :class:`Backend` for :func:`connect`.

    Raises:
        EngineValueError: If ``url`` is not an http(s) URL.

    """
    if not isinstance(url, str) or not re.match(r"^https?://", url):
        raise EngineValueError("url must be one SAS Viya URL starting with https:// or http://")
    cfg: dict[str, Any] = {"url": url, "authkey": "viya", "options": ["fullstimer"]}
    if context:
        cfg["context"] = context
    if not verify:
        cfg["verify"] = False
    return Backend("viya", cfg, url)


def sas94_iom(host: str, *, port: int = 8591, java: str | None = None) -> Backend:
    """SAS 9.4 over IOM (needs Java).

    Args:
        host: The SAS 9.4 host name.
        port: The IOM port (default 8591).
        java: Path to the Java executable (optional; auto-detected).

    Returns:
        A :class:`Backend` for :func:`connect`.

    Raises:
        EngineValueError: For an empty host or a port outside 1-65535.

    """
    _check_host(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= _MAX_PORT:
        raise EngineValueError("port must be an integer from 1 to 65535")
    cfg = {
        "java": java or _find_java(),
        "iomhost": host,
        "iomport": port,
        "authkey": "iom",
        "encoding": "utf-8",
    }
    return Backend("sas94_iom", cfg, host)


def sas94_ssh(host: str, saspath: str, *, ssh_user: str | None = None) -> Backend:
    """SAS 9.4 over SSH (key-based login).

    Args:
        host: The SAS 9.4 host name.
        saspath: The SAS executable path on that host.
        ssh_user: The SSH login user (optional).

    Returns:
        A :class:`Backend` for :func:`connect`.

    Raises:
        EngineValueError: For an empty host or saspath.

    """
    _check_host(host)
    if not isinstance(saspath, str) or not saspath:
        raise EngineValueError("saspath must be the path of the SAS executable on the host")
    cfg: dict[str, Any] = {
        "saspath": saspath,
        "ssh": _find_ssh(),
        "host": host,
        "encoding": "utf-8",
        "options": ["-fullstimer"],
    }
    if ssh_user:
        cfg["luser"] = ssh_user
    return Backend("sas94_ssh", cfg, host)


def _check_host(host: object) -> None:
    if not isinstance(host, str) or not host:
        raise EngineValueError("host must be one SAS 9.4 host name")


# How long a run waits for the engine's previous run to finish (as in R).
BUSY_WAIT_SECONDS = 30.0


def connect(  # noqa: PLR0913 - the deprecated keyword form keeps its parameters
    backend: Backend | str,
    *,
    license_ack: bool | None = None,
    region: str = "us1",
    url: str | None = None,
    context: str | None = None,
    verify: bool = True,
    host: str | None = None,
    port: int = 8591,
    saspath: str | None = None,
    ssh_user: str | None = None,
    java: str | None = None,
) -> SaspyEngine:
    """Build a SAS engine for one of the supported SAS systems (spec §6.6).

    Pass a backend: ``connect(oda("us1"))``, ``connect(viya(url))``,
    ``connect(sas94_iom(host))`` or ``connect(sas94_ssh(host, saspath))``.

    **Licence responsibility.** SAS is commercial software; you are responsible
    for holding a valid licence for the system you connect to (or, for ODA, for
    accepting its terms of use). A run fails with "SAS licence not acknowledged"
    unless ``license_ack=True`` or ``SASHINY_LICENSE_ACK=true`` is set.

    Credentials are never passed here. They come from ``~/.authinfo`` keyed by
    the backend's ``authkey``, or from ``SASHINY_SAS_USER`` /
    ``SASHINY_SAS_PASSWORD`` on hosted platforms such as Posit Connect.

    Args:
        backend: A :class:`Backend`. The old form, a profile name ``"oda"``,
            ``"viya"`` or ``"sas94"`` with the keyword arguments below, still
            works and emits a :class:`DeprecationWarning`.
        license_ack: ``True`` acknowledges that you are licensed to use the SAS
            system. ``None`` defers to ``SASHINY_LICENSE_ACK``.
        region: Deprecated form only.
        url: Deprecated form only.
        context: Deprecated form only.
        verify: Deprecated form only.
        host: Deprecated form only.
        port: Deprecated form only.
        saspath: Deprecated form only.
        ssh_user: Deprecated form only.
        java: Deprecated form only.

    Returns:
        A :class:`SaspyEngine` configured for the backend. No session starts yet.

    Raises:
        EngineValueError: If the backend or a required parameter is invalid.

    """
    if isinstance(backend, str):
        warnings.warn(
            "connect(profile, ...) is deprecated; pass a backend: connect(sashiny.oda()), "
            "viya(), sas94_iom() or sas94_ssh()",
            DeprecationWarning,
            stacklevel=2,
        )
        if backend == "oda":
            backend = oda(region, java=java)
        elif backend == "viya":
            if not url:
                raise EngineValueError("url is required for profile 'viya'")
            backend = viya(url, context=context, verify=verify)
        elif backend == "sas94":
            if not host:
                raise EngineValueError("host is required for profile 'sas94'")
            backend = (
                sas94_ssh(host, saspath, ssh_user=ssh_user)
                if saspath
                else sas94_iom(host, port=port, java=java)
            )
        else:
            raise EngineValueError(
                f"unknown profile {backend!r}; expected 'oda', 'viya' or 'sas94'"
            )
    elif (region, url, context, verify, host, port, saspath, ssh_user, java) != (
        "us1",
        None,
        None,
        True,
        None,
        8591,
        None,
        None,
        None,
    ):
        # As R's sas_connect(): a backend carries its own settings.
        raise EngineValueError("connection arguments go to the backend constructor, not connect()")
    if not isinstance(backend, Backend):
        raise EngineValueError("backend must come from oda(), viya(), sas94_iom() or sas94_ssh()")
    return SaspyEngine(backend.cfg, license_ack=license_ack)


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
        return {"default": None, "profiles": {}}
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
    # Anchor to an executed NOTE sentinel line, not a numbered source echo: the
    # line must start with "NOTE: SASHINY-END run=<id> syscc=<n>".
    m = re.search(rf"^NOTE: SASHINY-END run={re.escape(run_id)} syscc=(\d+)$", log, re.MULTILINE)
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
        raise EngineValueError(f"cfgname must be a Python identifier: {cfgname!r}")
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


def backend_of(cfg: dict[str, Any] | str | Path) -> str:
    """Identify the supported backend of a saspy configuration (spec §6.6).

    Args:
        cfg: A saspy configuration dict, or the path of a configuration file
            (accepted as is; you are responsible for its target).

    Returns:
        ``"oda"``, ``"viya"``, ``"sas94-iom"``, ``"sas94-ssh"`` or ``"cfgfile"``.

    Raises:
        ValueError: For any other configuration (local COM, local STDIO,
            unknown or ambiguous methods).

    """
    if isinstance(cfg, (str, Path)) and str(cfg):
        return "cfgfile"
    if not isinstance(cfg, dict) or not cfg:
        raise EngineValueError(
            f"cfg must be a dict or the path of a saspy configuration file; {_SUPPORTED}"
        )
    if "provider" in cfg or "colocal" in cfg:
        raise EngineValueError(f"local SAS (COM) connections are not supported; {_SUPPORTED}")
    http = "url" in cfg
    iom = "iomhost" in cfg
    ssh = "saspath" in cfg and "host" in cfg
    if http + iom + ssh != 1:
        if "saspath" in cfg and "host" not in cfg:
            raise EngineValueError(f"local SAS (STDIO) connections are not supported; {_SUPPORTED}")
        raise EngineValueError(
            "cfg must describe exactly one connection (url, iomhost, or saspath + host); "
            + _SUPPORTED
        )
    if http:
        if not re.match(r"^https?://", str(cfg["url"])):
            raise EngineValueError("the SAS Viya url must start with https:// or http://")
        return "viya"
    if iom:
        hosts = cfg["iomhost"] if isinstance(cfg["iomhost"], list) else [cfg["iomhost"]]
        if hosts and all(str(h).endswith(".oda.sas.com") for h in hosts):
            return "oda"
        if len(hosts) != 1:
            raise EngineValueError("a SAS 9.4 IOM configuration needs exactly one iomhost")
        return "sas94-iom"
    return "sas94-ssh"


def license_acknowledged(explicit: bool | None = None) -> bool:
    """Whether the user acknowledged licence responsibility (spec §6.6).

    An explicit ``license_ack`` wins; otherwise ``SASHINY_LICENSE_ACK`` set to
    ``true`` or ``1`` (case-insensitive) acknowledges it.
    """
    if explicit is not None:
        return bool(explicit)
    return os.environ.get("SASHINY_LICENSE_ACK", "").lower() in {"true", "1"}


def env_credentials(cfg: dict[str, Any] | str | Path) -> dict[str, str]:
    """Saspy session keyword arguments from ``SASHINY_SAS_USER``/``SASHINY_SAS_PASSWORD``.

    Used on hosted platforms such as Posit Connect (spec §6.7). The values go
    only to saspy, never to a file or a log. Empty for SSH (key-based login) or
    when either variable is unset.
    """
    user = os.environ.get("SASHINY_SAS_USER", "")
    password = os.environ.get("SASHINY_SAS_PASSWORD", "")
    if not user or not password or not isinstance(cfg, dict):
        return {}
    if "iomhost" in cfg:
        return {"omruser": user, "omrpw": password}
    if "url" in cfg:
        return {"user": user, "pw": password}
    return {}


def preflight(cfg: dict[str, Any], *, check_authinfo: bool = True) -> None:
    """Fail fast, with a clear message, on settings saspy would reject or prompt for.

    saspy prompts for a user id and password on stdin when the ``authkey`` is
    missing from the authinfo file, which would hang a Shiny app; and it reports
    a missing Java as an invalid configuration.

    Raises:
        RuntimeError: Java is missing for an IOM connection, or the ``authkey``
            has no entry in the authinfo file.

    """
    if "iomhost" in cfg and not cfg.get("java"):
        raise EngineRuntimeError(
            "Java was not found; IOM connections (ODA, SAS 9.4) need Java 8 or later. "
            "Install it, set JAVA_HOME, or pass java='/path/to/java'."
        )
    key = cfg.get("authkey")
    if key and check_authinfo:
        path = authinfo_path()
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
        if not any(line.split()[:1] == [key] for line in lines):
            raise EngineRuntimeError(
                f"no credentials for '{key}' in {path}. Add a line: "
                f"{key} user <user id> password <password>"
            )


class SaspyEngine(Engine):
    """A live SAS engine backed by saspy.

    One engine holds one SAS session, started on first use and reused across
    runs (each run resets WORK, spec §6.2). Use :class:`sashiny.Pool` to serve
    several users. Only SAS 9.4, SAS Viya and SAS OnDemand for Academics
    configurations are accepted (spec §6.6), and a run needs the licence
    acknowledgement described in :func:`sashiny.connect`.

    Args:
        cfg: A saspy configuration dict (written to a temporary ``sascfg``
            module) or the path of an existing saspy configuration file.
        cfgname: The configuration name inside that file.
        license_ack: ``True`` acknowledges that you are licensed to use the SAS
            system. ``None`` defers to ``SASHINY_LICENSE_ACK``.

    Raises:
        ValueError: If ``cfg`` is not a supported backend.

    """

    name = "saspy"
    version = __version__

    def __init__(
        self,
        cfg: dict[str, Any] | str | Path,
        cfgname: str = "sashiny",
        *,
        license_ack: bool | None = None,
    ) -> None:
        """Create a saspy engine; the SAS session starts on the first run."""
        self.backend = backend_of(cfg)
        self.cfg = cfg
        self.cfgname = cfgname
        self.license_ack = license_ack
        # Testing hook returning a fake saspy session; set only by the test
        # suite. Deliberately not a constructor argument: a public factory would
        # let a caller supply SAS logs that never came from SAS (spec §6.6).
        self._factory: Callable[[], Any] | None = None
        self._sas: Any = None
        self._sas_version_text: str | None = None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._choices: dict[tuple[str, str], list[dict[str, str]]] = {}
        self._generation = 0
        self._run_generation = threading.local()
        # One run at a time per engine (one SAS session), as in R (spec §6.5).
        self._busy = threading.Lock()

    # ------------------------------------------------------------------ session

    def _session(self) -> Any:
        # A timed-out run's worker must never open or reuse a session that a
        # newer run owns (spec §6.5). Each run carries an immutable generation;
        # once the engine has moved on, the stale worker raises instead.
        generation = getattr(self._run_generation, "value", None)
        if generation is not None and generation != self._generation:
            raise EngineRuntimeError("run was cancelled (timeout)")
        if self._sas is None:
            if not license_acknowledged(self.license_ack):
                raise LicenseError(LICENSE_MESSAGE)
            if self._factory is not None:
                sas = self._factory()
            else:
                credentials = env_credentials(self.cfg)
                if isinstance(self.cfg, dict):
                    preflight(self.cfg, check_authinfo=not credentials)
                import saspy  # noqa: PLC0415 - optional dependency

                if isinstance(self.cfg, dict):
                    self._tmp = tempfile.TemporaryDirectory(prefix="sashiny-cfg-")
                    cfgfile = str(_write_cfgfile(self.cfg, self.cfgname, Path(self._tmp.name)))
                else:
                    cfgfile = str(self.cfg)
                sas = saspy.SASsession(
                    cfgfile=cfgfile, cfgname=self.cfgname, results="HTML", **credentials
                )
            if generation is not None and generation != self._generation:
                with suppress(Exception):
                    sas.endsas()
                raise EngineRuntimeError("run was cancelled (timeout)")
            self._sas = sas
            try:
                self._check_session(sas)
                # ODA starts with NONOTES, which hides the run sentinels (spec 6.1).
                setup = sas.submit(SESSION_SETUP_CODE, results="TEXT")
                self._check_session(sas, setup.get("LOG", ""))
            except Exception:
                if self._sas is sas:
                    self._discard_session(background=True)
                raise
        return self._sas

    @staticmethod
    def _check_session(sas: Any, log: str = "") -> None:
        # SASpid is a string for a live saspy session. Internal test doubles
        # that do not model this attribute can still test the run protocol.
        if getattr(sas, "SASpid", True):
            return
        if not log:
            with suppress(Exception):
                log = sas.saslog()
        message = "could not start a SAS session: no SAS process attached"
        raise EngineRuntimeError(f"{message}: {log.strip()}" if log else message)

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
        from ..choices_cache import clear  # noqa: PLC0415 - avoid an import cycle

        clear(self)  # spec §6.4: the session is gone, as in R's sas_close()
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

    def _discard_session(self, background: bool = False) -> None:
        """Close the current session (if any) and forget it.

        Used when a run fails or times out: the session must be ended before the
        reference is lost, otherwise it leaks (spec §6.5). Session-scoped caches
        are invalid once the session is gone (spec §6.4 reads choices once per
        session); a replacement session must re-query them.

        ``background`` runs ``endsas()`` on a daemon thread so a blocking teardown
        cannot extend the whole-run deadline (spec §6.5); the caller returns
        promptly and the session is closed asynchronously.
        """
        from ..choices_cache import clear  # noqa: PLC0415 - avoid an import cycle

        clear(self)
        sas = self._sas
        self._sas = None
        self._choices.clear()
        self._sas_version_text = None
        if sas is not None:
            if background:

                def _end() -> None:
                    with suppress(Exception):
                        sas.endsas()

                threading.Thread(target=_end, name="sashiny-endsas", daemon=True).start()
            else:
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
        sas = self._session()
        try:
            self._submit(choices_code(source))
            df = self._session().sd2df("_sx_choices", "work")
            if df is None:
                raise EngineValueError(f"could not read choices from {source['dataset']}")
            lookup = {str(c).upper(): c for c in df.columns}
            values = [_choice_text(v) for v in df[lookup[value.upper()]]]
            labels = (
                values if label is None else [_choice_text(v) for v in df[lookup[label.upper()]]]
            )
            return [{"value": v, "label": lab or v} for v, lab in zip(values, labels, strict=True)]
        finally:
            if self._sas is sas:
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
        if not license_acknowledged(self.license_ack):
            refused = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
            refused.metadata["engine_error"] = LICENSE_MESSAGE
            return refused
        if not self._busy.acquire(timeout=BUSY_WAIT_SECONDS):
            busy = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
            busy.metadata["engine_error"] = "engine busy: another run is in progress"
            return busy
        try:
            return self._run_locked(contract, values, today, uploads, run_id)
        finally:
            self._busy.release()

    def _run_locked(
        self,
        contract: Contract,
        values: dict[str, Any],
        today: date,
        uploads: dict[str, Any] | None,
        run_id: str,
    ) -> Result:
        started = datetime.now(timezone.utc)
        timeout = float((contract.data.get("run") or {}).get("timeout_seconds", 300))

        # The SAS work blocks (saspy submit), so run it in a worker thread and
        # enforce the whole-run deadline (spec §2.3, §6.5). On timeout the session
        # is aborted and the pool discards it.
        box: dict[str, Result] = {}
        self._generation += 1
        generation = self._generation

        def work() -> None:
            self._run_generation.value = generation
            try:
                box["result"] = self._run(contract, values, today, uploads, run_id, started)
            except Exception as exc:  # reported on the result, never raised
                failed = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
                failed.metadata["engine_error"] = str(exc)
                box["result"] = failed

        thread = threading.Thread(target=work, name=f"sashiny-run-{run_id}", daemon=True)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            # Invalidate the stale worker's generation so it can never open or
            # reuse a session owned by a later run (spec §6.5).
            self._generation += 1
            self._discard_session(background=True)
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
        flags = {k: upload_supplied(v) for k, v in (uploads or {}).items()}
        try:
            cached = getattr(contract, "cached_choices", None)
            found = cached if cached is not None else self.choices(contract)
            override = {k: [c["value"] for c in v] for k, v in found.items()}
        except Exception as exc:  # reported on the result, never raised
            failed = Result.new(run_id, "error", engine=self.name, engine_version=self.version)
            failed.metadata["engine_error"] = str(exc)
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
            self._prepare(contract, uploads)
            res = self._submit(
                wrapper_code(data, macros, self._program(contract), run_id=run_id), "HTML"
            )
        except UploadError as exc:
            result = Result.new(run_id, "error", **base)
            result.metadata["issues"] = [{"code": "V014", "message": str(exc)}]
            return result
        except Exception as exc:
            result = Result.new(run_id, "error", **base)
            result.metadata["engine_error"] = str(exc)
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
        result.metadata["ended_at"] = utc_timestamp(ended)
        result.metadata["seconds"] = round((ended - started).total_seconds(), 2)
        result.metadata["backend"] = self.backend
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
            upload = resolve_upload((uploads or {}).get(iid), spec, contract.base_dir, iid)
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
            if is_paired(spec):
                outputs[oid] = self._collect_paired(oid, spec, html, errors)
                continue
            try:
                outputs[oid] = self._collect_one(oid, spec, html, res.get("LOG", ""))
            except Exception as exc:
                message = f"{oid}: {exc}"
                outputs[oid] = {"error": str(exc)}
                errors.append(message)
        return outputs, errors

    def _collect_paired(
        self, oid: str, spec: dict[str, Any], html: str, errors: list[str]
    ) -> dict[str, Any]:
        """Collect both parts of a paired output (§8.2 *paired*); each part fails alone."""
        select, chart = paired_parts(spec)
        value: dict[str, Any] = {}
        parts: dict[str, Callable[[], Any]] = {
            "sas": lambda: extract_plots(html, select),
            "sashiny": lambda: self._table(
                chart["from"],
                chart.get("columns"),
                int(chart.get("max_rows", 10000)),
                formatted=False,
            ),
        }
        for part, collect in parts.items():
            try:
                value[part] = collect()
            except Exception as exc:
                value[part] = {"error": str(exc)}
                errors.append(f"{oid}.{part}: {exc}")
        return value

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
        raise EngineValueError(f"unknown output type {kind}")

    def _table(
        self, ref: str, columns: list[str] | None, max_rows: int, *, formatted: bool
    ) -> dict[str, Any]:
        lib, mem = split_member(ref)
        sas = self._session()
        try:
            self._submit(table_meta_code(lib, mem))
            cols = sas.sd2df("_sx_cols", "work")
            if cols is None or len(cols) == 0:
                raise EngineValueError(f"dataset {lib}.{mem} not found")
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
                raise EngineValueError(f"could not read {lib}.{mem}")
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
            raise EngineValueError(f"cannot resolve the path of library {libref}")
        return m.group(1)

    def _fetch_file(self, remote: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="sashiny-dl-") as tmp:
            local = Path(tmp) / Path(remote.replace("\\", "/")).name
            res = self._session().download(str(local), remote)
            if isinstance(res, dict) and not res.get("Success", False):
                raise EngineValueError(f"download failed for {remote}")
            if not local.is_file():
                raise EngineValueError(f"download produced no file for {remote}")
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
            raise EngineValueError(f"unsupported download format {fmt}")
        return download_value(name, fmt, payload)
