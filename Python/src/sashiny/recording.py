"""Recordings: replayable run results (spec ``CONTRACT.md`` section 8.3).

A recording is written by a live engine (``SaspyEngine(record_to=...)``) and
replayed by :class:`sashiny.MockEngine`. The key depends only on the contract
bytes, the rendered macro values and the uploaded files, so recordings made in
R and in Python are interchangeable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .collect import recording_key
from .contract import Contract
from .result import Result

__all__ = [
    "contract_sha256",
    "key_for",
    "load_recording",
    "program_sha256",
    "save_recording",
    "upload_key_parts",
]

RECORDING_VERSION = 1


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def contract_sha256(contract: Contract) -> str:
    """SHA-256 of the contract YAML bytes on disk, or ``""`` for in-memory contracts."""
    if contract.path is None or not contract.path.is_file():
        return ""
    return _sha256(contract.path.read_bytes())


def program_sha256(contract: Contract) -> str:
    """SHA-256 of the SAS program bytes on disk."""
    return _sha256((contract.base_dir / contract.data["program"]).read_bytes())


def upload_key_parts(contract: Contract, files: dict[str, Path]) -> list[tuple[str, str]]:
    """``(input_id, sha256)`` pairs for supplied dataset inputs, in contract order."""
    parts = []
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if spec["type"] == "dataset" and iid in files:
            parts.append((iid, _sha256(Path(files[iid]).read_bytes())))
    return parts


def key_for(contract: Contract, macros: dict[str, str], files: dict[str, Path]) -> str:
    """Return the recording key for a run (§8.3)."""
    return recording_key(
        contract_sha256(contract), list(macros.items()), upload_key_parts(contract, files)
    )


def save_recording(directory: str | Path, key: str, result: Result) -> Path:
    """Write ``result`` as ``<directory>/<key>.json`` and return the path."""
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    payload = {
        "sashiny_recording": RECORDING_VERSION,
        "status": result.status,
        "log": result.log,
        "outputs": result.outputs,
        "sas_version": result.metadata.get("sas_version", ""),
        "contract_sha256": result.metadata.get("contract_sha256", ""),
        "program_sha256": result.metadata.get("program_sha256", ""),
        "macros": result.metadata.get("macros", {}),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = folder / f"{key}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def load_recording(directory: str | Path | None, key: str) -> dict[str, Any] | None:
    """Load ``<directory>/<key>.json``, or ``None`` when absent."""
    if directory is None:
        return None
    path = Path(directory) / f"{key}.json"
    if not path.is_file():
        return None
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
