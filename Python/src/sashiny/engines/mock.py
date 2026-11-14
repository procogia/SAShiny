"""Mock engine with record/replay for SAShiny.

Implements the engine interface without SAS. It replays recordings (spec
``CONTRACT.md`` §8.3) keyed by the contract bytes, the rendered macros and the
uploaded files. Recordings are written by a live engine
(``SaspyEngine(record_to=...)``) or with :meth:`MockEngine.save_recording`.
This powers CRAN/PyPI checks, examples, vignettes and the demo's offline
fallback (issue #5).
"""

from __future__ import annotations

import json
import uuid
from datetime import date
from pathlib import Path
from typing import Any

from ..contract import Contract
from ..recording import contract_sha256, key_for, load_recording, program_sha256
from ..result import Result
from ..upload import UploadError, UploadFile, _check_file, read_upload, resolve_upload
from ..values import render_values
from .base import Engine

__all__ = ["MockEngine"]


def _recording_key(
    contract: Contract, macros: dict[str, str], files: dict[str, Path] | None = None
) -> str:
    """Return the §8.3 recording key for a run."""
    return key_for(contract, macros, files or {})


def resolve_files(contract: Contract, uploads: dict[str, Any] | None) -> dict[str, Path]:
    """Resolve ``uploads`` entries to file paths (``True`` = the contract's sample).

    Each supplied file is checked per §7 step 1 (extension, existence, size); a
    bad file raises :class:`UploadError`, which the mock engine reports as ``V014``.
    """
    files: dict[str, Path] = {}
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if spec["type"] != "dataset":
            continue
        upload = resolve_upload((uploads or {}).get(iid), spec, contract.base_dir)
        if upload is not None:
            _check_file(upload, spec)
            files[iid] = upload.path
    return files


class MockEngine(Engine):
    """A mock engine that replays recorded results.

    Args:
        recordings_dir: Directory holding recording files (``<key>.json``).
            When ``None`` or when no recording matches, the engine returns an
            empty successful result with ``metadata["recording"] == "missing"``.
        record: Kept for backward compatibility; use
            ``SaspyEngine(record_to=...)`` to record live runs.
        choices: Choices for ``choices_from`` inputs, keyed by input id
            (strings or ``{"value", "label"}`` dicts), standing in for the
            SAS query of spec §6.4.

    """

    name = "mock"
    version = "0.1.0"

    def __init__(
        self,
        recordings_dir: str | Path | None = None,
        record: bool = False,
        choices: dict[str, list[Any]] | None = None,
    ) -> None:
        """Create a mock engine (see the class docstring for arguments)."""
        self.recordings_dir = Path(recordings_dir) if recordings_dir else None
        self.record = record
        self._choices = {
            iid: [c if isinstance(c, dict) else {"value": str(c), "label": str(c)} for c in items]
            for iid, items in (choices or {}).items()
        }

    def choices(self, contract: Contract) -> dict[str, list[dict[str, str]]]:  # noqa: D102
        inputs = contract.data.get("inputs") or {}
        return {
            iid: items
            for iid, items in self._choices.items()
            if "choices_from" in inputs.get(iid, {})
        }

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
        flags = {k: bool(v) for k, v in (uploads or {}).items()}
        override = {k: [c["value"] for c in v] for k, v in self.choices(contract).items()}
        macros, issues = render_values(
            contract.data, values, today, choices_override=override or None, uploads=flags
        )
        base: dict[str, Any] = {
            "contract_sha256": contract_sha256(contract),
            "program_sha256": program_sha256(contract),
            "macros": macros,
            "engine": self.name,
            "engine_version": self.version,
        }
        if issues:
            result = Result.new(run_id, "error", **base)
            result.metadata["issues"] = [{"code": i.code, "input": i.path} for i in issues]
            return result
        try:
            files = resolve_files(contract, uploads)
            # Run the full §7 conversion for every supplied dataset input, exactly
            # like the live engine, so a missing declared column, an unparseable
            # cell or an unreadable file is reported as V014 offline (spec §6.1
            # step 2 / §7).
            for iid, path in files.items():
                read_upload(UploadFile(path=path, name=path.name), contract.data["inputs"][iid])
        except UploadError as exc:
            result = Result.new(run_id, "error", **base)
            result.metadata["issues"] = [{"code": "V014", "message": str(exc)}]
            return result

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
