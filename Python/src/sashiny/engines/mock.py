"""Mock engine with record/replay for SAShiny.

Implements the engine interface without SAS. In replay mode it returns recorded
results keyed by the contract hash and rendered macros; in recording mode it
captures live runs for later replay. This powers CRAN/PyPI checks, examples,
vignettes and the demo's offline fallback (issue #5).
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from ..contract import Contract
from ..result import Result
from ..values import render_values
from .base import Engine

__all__ = ["MockEngine"]


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _contract_sha256(contract: Contract) -> str:
    """SHA-256 of the contract YAML bytes as stored on disk (spec §8).

    Returns an empty string for contracts built in memory without a source file.
    """
    if contract.path is None or not contract.path.is_file():
        return ""
    return _sha256(contract.path.read_bytes())


def _recording_key(contract: Contract, macros: dict[str, str]) -> str:
    """Deterministic key for a recording: contract hash + rendered macros."""
    contract_bytes = json.dumps(contract.data, sort_keys=True).encode("utf-8")
    macro_bytes = json.dumps(macros, sort_keys=True).encode("utf-8")
    return _sha256(contract_bytes + b"\n" + macro_bytes)


class MockEngine(Engine):
    """A mock engine that replays recorded results.

    Args:
        recordings_dir: Directory holding recording files (``<key>.json``).
            When ``None``, the engine returns an empty successful result for any
            run (useful for tests that only need the run protocol to succeed).
        record: When ``True``, write a recording for each run instead of
            replaying. Used to capture live results for the offline fallback.

    """

    name = "mock"
    version = "0.0.1"

    def __init__(self, recordings_dir: str | Path | None = None, record: bool = False) -> None:
        """Create a mock engine.

        Args:
            recordings_dir: Directory holding recording files (`<key>.json`).
            record: When `True`, write recordings instead of replaying.

        """
        self.recordings_dir = Path(recordings_dir) if recordings_dir else None
        self.record = record

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
                run_id,
                "error",
                contract_sha256=_contract_sha256(contract),
                program_sha256=_sha256(contract.base_dir.joinpath(data["program"]).read_bytes()),
                macros=macros,
                engine=self.name,
                engine_version=self.version,
            )

        key = _recording_key(contract, macros)
        recording = self._load_recording(key)
        if recording is not None:
            return self._replay(recording, run_id, macros, contract)

        # No recording: return an empty successful result.
        return Result.new(
            run_id,
            "success",
            contract_sha256=_contract_sha256(contract),
            program_sha256=_sha256(contract.base_dir.joinpath(data["program"]).read_bytes()),
            macros=macros,
            engine=self.name,
            engine_version=self.version,
        )

    def _load_recording(self, key: str) -> dict[str, Any] | None:
        if self.recordings_dir is None:
            return None
        path = self.recordings_dir / f"{key}.json"
        if not path.is_file():
            return None
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data

    def _replay(
        self,
        recording: dict[str, Any],
        run_id: str,
        macros: dict[str, str],
        contract: Contract,
    ) -> Result:
        result = Result.new(
            run_id,
            recording.get("status", "success"),
            contract_sha256=recording.get("contract_sha256", ""),
            program_sha256=recording.get("program_sha256", ""),
            macros=macros,
            engine=self.name,
            engine_version=self.version,
            sas_version=recording.get("sas_version", ""),
        )
        result.log = recording.get("log", "")
        result.outputs = recording.get("outputs", {})
        return result

    def save_recording(
        self,
        contract: Contract,
        macros: dict[str, str],
        recording: dict[str, Any],
    ) -> None:
        """Write a recording for later replay (recording mode)."""
        if self.recordings_dir is None:
            raise ValueError("recordings_dir is not set")
        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        key = _recording_key(contract, macros)
        (self.recordings_dir / f"{key}.json").write_text(
            json.dumps(recording, indent=2, sort_keys=True), encoding="utf-8"
        )
