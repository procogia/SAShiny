"""Replay of recordings made on a live, licensed SAS system (spec ``CONTRACT.md`` §6.6 (a)).

The replay engine serves recordings (§8.3) instead of submitting programs to
SAS, for offline demos and static sites. A recording is replayed only when it
carries provenance from a licensed SAS run (the SAS version, the recording
time, and the SHA-256 of the contract and program it was made from, which must
match the files on disk). Every replayed result is labelled as a replay.
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .. import __version__
from ..contract import Contract
from ..recording import key_for
from ..result import Result
from ._offline import prepare_offline_run
from .base import Engine

__all__ = ["MISSING_MESSAGE", "ReplayEngine", "replay", "replay_problem"]

MISSING_MESSAGE = "no recording of this run: these inputs were not recorded on SAS"


def replay_problem(recording: dict[str, Any], contract_sha256: str, program_sha256: str) -> str:
    """Return why a recording may not be replayed, or ``""`` (§6.6 (a), checked in order)."""

    def filled(name: str) -> bool:
        value = recording.get(name)
        return isinstance(value, str) and value != ""

    version = recording.get("sashiny_recording")
    if isinstance(version, bool) or version != 1:
        return "it is not a version 1 SAShiny recording"
    if not filled("sas_version"):
        return "it has no SAS version"
    if not filled("recorded_at"):
        return "it has no recording time"
    if not filled("contract_sha256") or recording["contract_sha256"] != contract_sha256:
        return "it was made from a different contract"
    if not filled("program_sha256") or recording["program_sha256"] != program_sha256:
        return "it was made from a different version of the program"
    return ""


class ReplayEngine(Engine):
    """Replays recordings of runs made on a live, licensed SAS system.

    Create it with :func:`sashiny.replay`. It runs no ``choices_from`` query
    and needs no licence acknowledgement, because it submits nothing to SAS.

    Args:
        recordings_dir: Directory holding the recording files (``<key>.json``).

    """

    name = "replay"
    version = __version__

    def __init__(self, recordings_dir: str | Path) -> None:
        """Create a replay engine over ``recordings_dir``."""
        if recordings_dir is None or str(recordings_dir) == "":
            raise TypeError("recordings_dir must be a directory path")
        self.recordings_dir = Path(recordings_dir)

    def __repr__(self) -> str:
        """Show the recordings folder."""
        return f"<sashiny replay engine> recordings: {self.recordings_dir}"

    def run(
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Result:
        """Replay the recording of this run, or return an error result saying why not."""
        today = today or date.today()
        run_id = run_id or str(uuid.uuid4())
        prep = prepare_offline_run(self, contract, values, today, uploads, run_id, self.name)
        if prep.result is not None:
            return prep.result
        base = prep.base

        def fail(recording: str, message: str) -> Result:
            result = Result.new(run_id, "error", **base)
            result.metadata["recording"] = recording
            result.metadata["engine_error"] = message
            return result

        path = self.recordings_dir / f"{key_for(contract, prep.macros, prep.files)}.json"
        if not path.is_file():
            return fail("missing", MISSING_MESSAGE)
        try:
            recording = json.loads(path.read_text(encoding="utf-8"))
            problem = "" if isinstance(recording, dict) else "it is not valid JSON"
        except (ValueError, UnicodeDecodeError):
            recording, problem = {}, "it is not valid JSON"
        problem = problem or replay_problem(
            recording, base["contract_sha256"], base["program_sha256"]
        )
        if problem:
            return fail("refused", f"recording not replayed: {problem}")
        status = recording.get("status", "success")
        result = Result.new(run_id, status, **{**base, "sas_version": recording["sas_version"]})
        result.metadata["recording"] = "replayed"
        result.metadata["recorded_at"] = recording["recorded_at"]
        result.metadata["notice"] = (
            f"Replayed from {recording['sas_version']}, recorded {recording['recorded_at']}."
        )
        result.log = recording.get("log", "")
        result.outputs = recording.get("outputs", {})
        return result


def replay(recordings_dir: str | Path) -> ReplayEngine:
    """Replay recordings of runs made on a live, licensed SAS system (spec §6.6 (a)).

    A recording is replayed only when it carries provenance from a licensed SAS
    run: ``sas_version`` (``&SYSVLONG``), ``recorded_at``, and the SHA-256 of the
    contract and program it was made from, which must match the files on disk.
    Otherwise the run returns an error result whose ``metadata["engine_error"]``
    gives the reason. A replayed result has ``metadata["recording"] ==
    "replayed"`` and a ``metadata["notice"]`` such as ``"Replayed from
    9.04.01M0P061913, recorded 2015-07-30T12:00:00Z."``, which the module's
    status text shows. Write recordings with :func:`sashiny.record`.

    Args:
        recordings_dir: Directory holding the recording files (``<key>.json``).

    Returns:
        A :class:`ReplayEngine`, accepted by :func:`sashiny.run`, the Shiny
        module, :func:`sashiny.app` and :class:`sashiny.Pool`.

    """
    return ReplayEngine(recordings_dir)
