"""Value and file preparation shared by the engines that do not submit to SAS.

The replay engine (:mod:`sashiny.engines.replay`) and the internal test mock
validate values and dataset files exactly like a live engine (spec §4, §6.1
step 2, §7) before they look up a recording (§8.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .. import __version__
from ..contract import Contract
from ..recording import contract_sha256, program_sha256
from ..result import Result
from ..upload import UploadError, UploadFile, _check_file, read_upload, resolve_upload
from ..values import render_values

if TYPE_CHECKING:
    from .base import Engine

__all__ = ["Prepared", "prepare_offline_run", "resolve_files"]


def resolve_files(contract: Contract, uploads: dict[str, Any] | None) -> dict[str, Path]:
    """Resolve ``uploads`` entries to file paths (``True`` = the contract's sample).

    Each supplied file is checked per §7 step 1 (extension, existence, size); a
    bad file raises :class:`UploadError`, which offline engines report as ``V014``.
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


@dataclass
class Prepared:
    """The outcome of :func:`prepare_offline_run`.

    ``result`` is set when the run fails validation; otherwise ``macros`` and
    ``files`` feed the recording key and ``base`` the result metadata.
    """

    base: dict[str, Any]
    macros: dict[str, str]
    files: dict[str, Path] = field(default_factory=dict)
    result: Result | None = None


def prepare_offline_run(  # noqa: PLR0913, PLR0917 - mirrors Engine.run plus the engine name
    engine: Engine,
    contract: Contract,
    values: dict[str, Any],
    today: date,
    uploads: dict[str, Any] | None,
    run_id: str,
    engine_name: str,
) -> Prepared:
    """Validate and render ``values`` and the dataset files for an offline run."""
    flags = {k: bool(v) for k, v in (uploads or {}).items()}
    found = getattr(contract, "cached_choices", None) or engine.choices(contract)
    override = {k: [c["value"] for c in v] for k, v in found.items()}
    macros, issues = render_values(
        contract.data, values, today, choices_override=override or None, uploads=flags
    )
    base: dict[str, Any] = {
        "contract_sha256": contract_sha256(contract),
        "program_sha256": program_sha256(contract),
        "macros": macros,
        "engine": engine_name,
        "engine_version": __version__,
    }
    prepared = Prepared(base=base, macros=macros)
    if issues:
        result = Result.new(run_id, "error", **base)
        result.metadata["issues"] = [{"code": i.code, "input": i.path} for i in issues]
        prepared.result = result
        return prepared
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
        prepared.result = result
        return prepared
    prepared.files = files
    return prepared
