"""Internal offline mock engine: a TEST FIXTURE, not part of the public API.

PyPI and CI checks have no SAS, so the test suite needs a way to exercise the
Shiny module, the pool and result handling without one. This engine replays
hand-written recordings (spec ``CONTRACT.md`` §8.3) for that purpose only. It is
not exported, it refuses to run outside pytest, and the public entry points
accept only live, replay and registered engines outside tests
(:func:`check_engine`). Unlike the public replay engine
(:func:`sashiny.replay`), it does not check provenance, so users cannot feed it
logs or results that did not come from a licensed SAS system (spec §6.6).
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from .. import __version__
from ..contract import Contract
from ..recording import key_for, load_recording
from ..result import Result
from ._offline import prepare_offline_run, resolve_files
from .base import Engine, testing

__all__ = ["MockEngine", "resolve_files"]


def _require_testing() -> None:
    if not testing():
        raise RuntimeError(
            "the mock engine is an internal test fixture; connect to SAS with sashiny.connect()"
        )


def _recording_key(
    contract: Contract, macros: dict[str, str], files: dict[str, Path] | None = None
) -> str:
    """Return the §8.3 recording key for a run."""
    return key_for(contract, macros, files or {})


class MockEngine(Engine):
    """The internal mock engine (tests only); replays recorded results.

    Args:
        recordings_dir: Directory holding recording files (``<key>.json``).
            When ``None`` or when no recording matches, the engine returns an
            empty successful result with ``metadata["recording"] == "missing"``.
        choices: Choices for ``choices_from`` inputs, keyed by input id
            (strings or ``{"value", "label"}`` dicts), standing in for the
            SAS query of spec §6.4.

    """

    name = "mock"
    version = __version__

    def __init__(
        self,
        recordings_dir: str | Path | None = None,
        choices: dict[str, list[Any]] | None = None,
    ) -> None:
        """Create a mock engine (see the class docstring for arguments)."""
        _require_testing()
        self.recordings_dir = Path(recordings_dir) if recordings_dir else None
        self._choices = {
            iid: [c if isinstance(c, dict) else {"value": str(c), "label": str(c)} for c in items]
            for iid, items in (choices or {}).items()
        }

    def choices(self, contract: Contract) -> dict[str, list[dict[str, str]]]:
        inputs = contract.data.get("inputs") or {}
        return {
            iid: items
            for iid, items in self._choices.items()
            if "choices_from" in inputs.get(iid, {})
        }

    def run(
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Result:
        _require_testing()
        today = today or date.today()
        run_id = run_id or str(uuid.uuid4())
        prep = prepare_offline_run(self, contract, values, today, uploads, run_id, self.name)
        if prep.result is not None:
            return prep.result
        base, macros, files = prep.base, prep.macros, prep.files
        recording = load_recording(self.recordings_dir, _recording_key(contract, macros, files))
        if recording is None:
            result = Result.new(run_id, "success", **base)
            result.metadata["recording"] = "missing"
            return result
        result = Result.new(
            run_id, recording.get("status", "success"), **{**base, "engine": self.name}
        )
        result.metadata["sas_version"] = recording.get("sas_version", "")
        result.metadata["recording"] = "replayed"
        result.metadata["recorded_at"] = recording.get("recorded_at", "")
        result.log = recording.get("log", "")
        result.outputs = recording.get("outputs", {})
        return result

    def save_recording(
        self,
        contract: Contract,
        macros: dict[str, str],
        recording: dict[str, Any],
        files: dict[str, Path] | None = None,
    ) -> None:
        """Write a raw recording dict for later replay.

        Raises:
            ValueError: If ``recordings_dir`` is not set.

        """
        if self.recordings_dir is None:
            raise ValueError("recordings_dir is not set")
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        key = _recording_key(contract, macros, files)
        payload = {"sashiny_recording": 1, **recording}
        (self.recordings_dir / f"{key}.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
