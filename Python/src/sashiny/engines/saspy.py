"""saspy engine with selectable connection profiles (issue #6).

Implements the run protocol (spec §6.1), dataset upload conversion (§7), result
collection (§8) and run status (§6.5) against live SAS 9.4 / Viya via saspy.
Connection profiles are chosen per app or session; credentials come only from
``~/.authinfo`` or environment variables, never from the contract.

Live verification is deferred to the live SAS check reports (issue #11); this
module implements the interface and profile loading.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from ..contract import Contract
from ..result import Result
from ..values import render_values
from ..wrapper import reset_code, wrapper_code
from .base import Engine

__all__ = ["SaspyEngine", "load_profiles"]

CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
# syscc threshold above which a run is an error (spec §6.5).
SYSCC_ERROR = 4


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


class SaspyEngine(Engine):
    """A live SAS engine backed by saspy.

    Args:
        cfg: The saspy configuration dict (or a path to a config file).
        cfgname: The saspy config name.

    """

    name = "saspy"
    version = "0.0.1"

    def __init__(self, cfg: dict[str, Any] | str | Path, cfgname: str = "sashiny") -> None:
        """Create a saspy engine.

        Args:
            cfg: The saspy configuration dict (or a path to a config file).
            cfgname: The saspy config name.

        """
        self.cfg = cfg
        self.cfgname = cfgname
        self._sas: Any = None

    def _session(self) -> Any:
        if self._sas is None:
            import saspy  # noqa: PLC0415 - optional dependency

            self._sas = saspy.SASsession(
                cfgfile=str(self.cfg), cfgname=self.cfgname, results="HTML"
            )
        return self._sas

    def run(  # noqa: D102 - documented on the base class
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, bool] | None = None,
        run_id: str | None = None,
    ) -> Result:
        today = today or date.today()
        run_id = run_id or str(uuid.uuid4())
        data = contract.data
        macros, issues = render_values(data, values, today, uploads=uploads)
        if issues:
            return Result.new(
                run_id, "error", macros=macros, engine=self.name, engine_version=self.version
            )

        sas = self._session()
        uploads = uploads or {}
        if (data.get("run") or {}).get("reset_work", True):
            sas.submit(reset_code(data), results="TEXT")
        for iid, spec in (data.get("inputs") or {}).items():
            if spec["type"] == "dataset" and uploads.get(iid) and "sample" in spec:
                self._upload_sample(contract.base_dir, spec)

        program = (contract.base_dir / data["program"]).read_bytes()
        t0 = time.monotonic()
        res = sas.submit(wrapper_code(data, macros, program, run_id=run_id), results="HTML")
        status, syscc = run_status(res["LOG"], run_id)
        result = Result.new(
            run_id,
            status,
            macros=macros,
            engine=self.name,
            engine_version=self.version,
            sas_version=self._sas_version(),
        )
        result.log = res["LOG"]
        result.outputs = self._collect(data, res, sas)
        result.metadata["seconds"] = round(time.monotonic() - t0, 2)
        result.metadata["syscc"] = syscc
        return result

    def _sas_version(self) -> str:
        try:
            res = self._session().submit("%put SXVER=&sysvlong;", results="TEXT")
            m = re.search(r"SXVER=(\S+)", res["LOG"])
            return m.group(1) if m else ""
        except Exception:  # pragma: no cover - best effort
            return ""

    def _upload_sample(self, base: Path, spec: dict[str, Any]) -> None:
        import pandas as pd  # noqa: PLC0415 - optional dependency

        df = pd.read_csv(base / spec["sample"], dtype=str, keep_default_na=False)
        date_cols: dict[str, str] = {}
        for col in spec.get("columns", []):
            name = next(c for c in df.columns if c.upper() == col["name"].upper())
            if col["type"] == "numeric":
                df[name] = pd.to_numeric(df[name].replace("", None))
            elif col["type"] == "date":
                df[name] = pd.to_datetime(df[name].replace("", None), format="%Y-%m-%d")
                date_cols[name] = "date"
        libref, member = spec["target"].split(".")
        self._session().df2sd(df, table=member, libref=libref, datetimes=date_cols)

    def _collect(self, data: dict[str, Any], res: dict[str, Any], sas: Any) -> dict[str, Any]:
        """Collect outputs per spec §8 (best-effort; refined in #11)."""
        outputs: dict[str, Any] = {}
        for oid, spec in (data.get("outputs") or {}).items():
            kind = spec["type"]
            if kind == "html":
                outputs[oid] = res.get("LST", "")
            elif kind == "log":
                outputs[oid] = res.get("LOG", "")
        return outputs

    def close(self) -> None:
        """Close the underlying SAS session."""
        if self._sas is not None:
            self._sas.endsas()
            self._sas = None
