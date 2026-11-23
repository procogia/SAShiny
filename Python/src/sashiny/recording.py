"""Recording keys and run hashes (spec ``CONTRACT.md`` sections 8.3 and 8.4).

Apps write recordings of live or registered engines' results with
:func:`record` and replay them with :func:`sashiny.replay`, which checks their
provenance (spec §6.6). The internal test mock also replays hand-written
recordings. Live engines never write recordings on their own. The key depends
only on the contract bytes, the rendered macro values and the uploaded files,
so recordings written by R and Python are interchangeable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .collect import recording_key
from .contract import Contract
from .errors import EngineError
from .result import Result, utc_timestamp

__all__ = [
    "contract_sha256",
    "key_for",
    "load_recording",
    "program_sha256",
    "record",
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
        "recorded_at": utc_timestamp(),
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


def record(
    directory: str | Path,
    contract: Contract | str | Path,
    result: Result,
    uploads: dict[str, Any] | None = None,
) -> Path:
    """Write a live run's ``result`` as a recording (spec §6.6, §8.3) and return its path.

    The file name is the recording key of the run's rendered macros
    (``result.metadata["macros"]``) and dataset files, so recordings made in R
    and Python are interchangeable; :func:`sashiny.replay` replays them. Empty
    ``macros`` and ``outputs`` are written as JSON objects.

    Args:
        directory: Folder to write into (created if needed).
        contract: The contract the result was run from (or its path).
        result: A result from a live or registered engine.
        uploads: The ``uploads`` the run was given (dataset input files).

    Raises:
        EngineError: When the result has no SAS version, is itself a replay or a
            cache hit, the contract has no file on disk, or the result's contract
            or program SHA-256 differs from the files on disk.

    """
    from .contract import load  # noqa: PLC0415 - avoid an import cycle
    from .engines._offline import resolve_files  # noqa: PLC0415

    if not isinstance(contract, Contract):
        contract = load(contract)
    meta = result.metadata

    def refuse(reason: str) -> EngineError:
        return EngineError(f"cannot record this result: {reason}")

    if not meta.get("sas_version"):
        raise refuse("it has no SAS version, so it did not come from a live SAS run")
    if meta.get("recording") is not None:
        raise refuse(f'it is itself a replay (metadata["recording"] is "{meta["recording"]}")')
    if meta.get("cache_hit"):
        raise refuse("it is a result-cache hit")
    csha = contract_sha256(contract)
    if not csha:
        raise refuse("the contract has no file on disk")
    if meta.get("contract_sha256", "") != csha:
        raise refuse("it was made from a different contract")
    psha = program_sha256(contract)
    if meta.get("program_sha256", "") != psha:
        raise refuse("it was made from a different version of the program")
    macros = dict(meta.get("macros") or {})
    files = resolve_files(contract, uploads)
    payload = {
        "sashiny_recording": RECORDING_VERSION,
        "status": result.status,
        "log": result.log or "",
        "outputs": result.outputs or {},
        "sas_version": meta["sas_version"],
        "contract_sha256": csha,
        "program_sha256": psha,
        "macros": macros,
        "recorded_at": utc_timestamp(),
    }
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key_for(contract, macros, files)}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
