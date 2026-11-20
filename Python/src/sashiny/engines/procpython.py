"""In-session engine for PROC PYTHON (spec §6.5, §6.6; #128).

Inside a SAS Viya or SAS 9.4M9+ job, PROC PYTHON injects a ``SAS`` callback
object into its Python session. This engine runs a contract through that object
instead of a separate saspy session, for batch use (scheduled reports, flows):

.. code-block:: sas

    proc python;
    submit;
    import sashiny
    eng = sashiny.connect_in_session(SAS, license_ack=True, own_session=True)
    res = sashiny.run("/data/apps/demo/demo.sashiny.yml", {"make": "Audi"}, eng)
    endsubmit;
    run;

The run shares the user's SAS session, so the §6.2 reset (which empties WORK) is
allowed only with ``own_session=True``. A timeout cannot abort the parent session:
the engine stops waiting, returns an error and refuses later runs (§6.5).
"""

from __future__ import annotations

import itertools
import re
import shutil
import threading
import uuid
from pathlib import Path
from typing import Any

from ..contract import Contract
from ..result import Result
from .saspy import LICENSE_MESSAGE, SESSION_SETUP_CODE, SaspyEngine, license_acknowledged

__all__ = ["ProcPythonEngine", "connect_in_session"]

RESET_REFUSED = (
    "reset_work refused: the in-session engine shares your SAS session, so emptying WORK "
    "needs connect_in_session(..., own_session=True); otherwise set run.reset_work: false"
)
DEAD_MESSAGE = (
    "in-session engine stopped after a timeout: the SAS job that started it must be ended "
    "by its scheduler (spec §6.5)"
)
_SAFE_PATH = re.compile(r"^[^'\"\r\n;]+$")


class _InSessionSAS:
    """Present the PROC PYTHON ``SAS`` object with the saspy calls the engine uses.

    ``submit`` routes the log and listing to files in WORK (``PROC PRINTTO`` and
    ``ODS HTML5``) and reads them back, because the callback does not return them.
    """

    def __init__(self, sas: Any) -> None:
        self.sas = sas
        self._seq = itertools.count(1)
        self._work: Path | None = None

    def workpath(self) -> Path:
        if self._work is None:
            path = None
            if hasattr(self.sas, "workpath"):
                path = self.sas.workpath()
            if not path:
                self.sas.submit("%let _sashiny_work=%sysfunc(pathname(work));")
                path = self.sas.symget("_sashiny_work")
            text = str(path).strip()
            if not text or not _SAFE_PATH.match(text):
                raise RuntimeError(f"cannot use the WORK path {text!r}")
            self._work = Path(text)
        return self._work

    def submit(self, code: str, results: str = "TEXT") -> dict[str, str]:
        n = next(self._seq)
        work = self.workpath()
        log = work / f"_sashiny_{n}.log"
        lst = work / f"_sashiny_{n}.html"
        head = [f'proc printto log="{log}" new; run;']
        tail = []
        if results.upper() == "HTML":
            head.append(f'ods html5 file="{lst}" options(bitmap_mode="inline");')
            tail.append("ods html5 close;")
        tail.append("proc printto; run;")
        self.sas.submit("\n".join([*head, code, *tail]) + "\n")
        out = {"LOG": _read_text(log), "LST": _read_text(lst) if results.upper() == "HTML" else ""}
        for path in (log, lst):
            path.unlink(missing_ok=True)
        return out

    def sd2df(self, table: str, libref: str = "WORK", dsopts: dict[str, Any] | None = None) -> Any:
        options = []
        if dsopts:
            if dsopts.get("obs") is not None:
                options.append(f"obs={int(dsopts['obs'])}")
            if dsopts.get("keep"):
                options.append(f"keep={dsopts['keep']}")
        name = f"{libref}.{table}" + (f"({' '.join(options)})" if options else "")
        try:
            return self.sas.sd2df(name)
        except Exception:  # saspy returns None for a missing data set
            return None

    def df2sd(self, df: Any, table: str, libref: str, datetimes: dict[str, str]) -> None:
        # The callback has no datetimes option; SAS infers date/datetime columns.
        self.sas.df2sd(df, f"{libref}.{table}")

    def download(self, localfile: str, remotefile: str, overwrite: bool = True) -> dict[str, Any]:
        source = Path(remotefile)
        if not source.is_file():
            return {"Success": False, "LOG": f"{remotefile} not found"}
        shutil.copyfile(source, localfile)
        return {"Success": True, "LOG": ""}

    def endsas(self) -> None:
        """Never end the parent SAS session."""


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


class ProcPythonEngine(SaspyEngine):
    """A live SAS engine that runs inside a PROC PYTHON job (spec §6.6).

    Args:
        sas: The ``SAS`` callback object of PROC PYTHON.
        license_ack: ``True`` acknowledges that you are licensed to use the SAS
            system. ``None`` defers to ``SASHINY_LICENSE_ACK``.
        own_session: ``True`` confirms that the SAS job exists only for this
            run, which allows the §6.2 reset of WORK and macro variables.

    """

    name = "procpython"
    version = "0.1.0"

    def __init__(self, sas: Any, *, license_ack: bool | None = None, own_session: bool = False):
        """Wrap the PROC PYTHON ``SAS`` object; nothing is submitted until the first run."""
        if sas is None or not callable(getattr(sas, "submit", None)):
            raise TypeError("connect_in_session() needs the SAS object of PROC PYTHON")
        # Not SaspyEngine.__init__: there is no saspy configuration to validate.
        self.backend = "in-session"
        self.cfg: dict[str, Any] = {}
        self.cfgname = "in-session"
        self.license_ack = license_ack
        self._factory = None
        self._sas = None
        self._sas_version_text = None
        self._tmp = None
        self._choices = {}
        self._generation = 0
        self._run_generation = threading.local()
        self.own_session = own_session
        self._callback = sas
        self._dead = False

    def _session(self) -> Any:
        if self._dead:
            raise RuntimeError(DEAD_MESSAGE)
        generation = getattr(self._run_generation, "value", None)
        if generation is not None and generation != self._generation:
            raise RuntimeError("run was cancelled (timeout)")
        if self._sas is None:
            if not license_acknowledged(self.license_ack):
                raise RuntimeError(LICENSE_MESSAGE)
            self._sas = _InSessionSAS(self._callback)
            self._sas.submit(SESSION_SETUP_CODE, results="TEXT")
        return self._sas

    def _discard_session(self, background: bool = False) -> None:
        from ..choices_cache import clear  # noqa: PLC0415 - avoid an import cycle

        clear(self)
        self._choices.clear()
        self._sas_version_text = None
        if background:
            # Only a timeout discards in the background: the parent session
            # cannot be aborted from here, so this engine stops for good.
            self._dead = True

    def _remote_dir(self, libref: str) -> str:
        if libref.lower() == "work":
            return str(self._session().workpath())
        return super()._remote_dir(libref)

    def close(self) -> None:
        """Forget the session; the parent SAS session is never ended."""
        self._choices.clear()
        self._sas_version_text = None
        self._sas = None

    def run(  # noqa: D102 - documented on the base class
        self,
        contract: Contract,
        values: dict[str, Any],
        **kwargs: Any,
    ) -> Result:
        run_id = kwargs.get("run_id")
        if self._dead:
            return self._refused(run_id, DEAD_MESSAGE)
        if (contract.data.get("run") or {}).get("reset_work", True) and not self.own_session:
            return self._refused(run_id, RESET_REFUSED)
        return super().run(contract, values, **kwargs)

    def _refused(self, run_id: str | None, message: str) -> Result:
        result = Result.new(
            run_id or str(uuid.uuid4()), "error", engine=self.name, engine_version=self.version
        )
        result.metadata["engine_error"] = message
        result.metadata["backend"] = self.backend
        return result


def connect_in_session(
    sas: Any, *, license_ack: bool | None = None, own_session: bool = False
) -> ProcPythonEngine:
    """Return an engine that runs contracts inside the current PROC PYTHON job.

    Args:
        sas: The ``SAS`` object that PROC PYTHON injects into its Python session.
        license_ack: ``True`` acknowledges that you are licensed to use the SAS
            system (spec §6.6). ``None`` defers to ``SASHINY_LICENSE_ACK``.
        own_session: ``True`` confirms that the SAS job exists only for this
            run. Required for contracts with ``run.reset_work: true`` (the
            default), because the reset empties WORK and deletes macro variables.

    Returns:
        A :class:`ProcPythonEngine`. Batch only: there is no pool.

    """
    return ProcPythonEngine(sas, license_ack=license_ack, own_session=own_session)
