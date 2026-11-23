"""Registered engines (spec ``CONTRACT.md`` §6.6 (b)).

An app can register its own :class:`sashiny.Engine` subclass, for example one
that runs SAS 9.4 in batch on the same machine. The public entry points then
accept engines of that class. A registered engine MUST execute every run on a
live, licensed SAS system; SAShiny cannot verify this, so registration needs an
explicit ``license_ack=True``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .. import __version__
from ..contract import Contract
from ..errors import EngineError, LicenseError
from ..recording import contract_sha256, program_sha256
from ..result import Result
from .base import Engine

__all__ = [
    "engine_result",
    "is_registered",
    "register_engine",
    "registered_engines",
    "unregister_engine",
]

_REGISTRY: dict[type, str] = {}


def _qualname(cls: type) -> str:
    return f"{cls.__module__}.{cls.__qualname__}"


def register_engine(cls: type, *, license_ack: bool = False, description: str = "") -> type:
    """Register an engine class that runs on a live, licensed SAS system (spec §6.6 (b)).

    After registration, :func:`sashiny.run`, the Shiny module, :func:`sashiny.app`
    and :class:`sashiny.Pool` accept instances of ``cls`` (and its subclasses).

    A registered engine MUST execute every run on a live SAS system that you are
    licensed to use, and the log and outputs it returns MUST be the ones that SAS
    run produced. SAShiny cannot verify this: ``license_ack=True`` is your
    acknowledgement. ``SASHINY_LICENSE_ACK`` does not register an engine.

    Args:
        cls: A subclass of :class:`sashiny.Engine` that is not defined in SAShiny.
        license_ack: Must be ``True``.
        description: Names the SAS system the engine runs on, for example
            ``"SAS 9.4M0 batch on this machine"``.

    Returns:
        ``cls``, so the function also works as a class decorator through
        :func:`functools.partial`.

    Raises:
        LicenseError: Without ``license_ack=True``.
        EngineError: For a class that is not an :class:`Engine` subclass, one of
            SAShiny's own classes, or an empty description.

    """
    if not isinstance(cls, type) or not issubclass(cls, Engine):
        raise EngineError("cls must be a subclass of sashiny.Engine")
    if cls.__module__ == "sashiny" or cls.__module__.startswith("sashiny."):
        raise EngineError(
            f"class {cls.__qualname__} is one of SAShiny's own engine classes and cannot be "
            "registered"
        )
    if license_ack is not True:
        raise LicenseError(
            "SAS licence not acknowledged: register an engine only if it runs every program on a "
            "live SAS system you are licensed to use, and confirm this with license_ack=True"
        )
    if not isinstance(description, str) or not description.strip():
        raise EngineError("description must name the SAS system the engine runs on")
    _REGISTRY[cls] = description.strip()
    return cls


def unregister_engine(cls: type) -> type:
    """Remove a registration made with :func:`register_engine` (no error if absent)."""
    _REGISTRY.pop(cls, None)
    return cls


def registered_engines() -> dict[str, str]:
    """Return the registered engine classes (``module.QualName``) and their descriptions."""
    return {_qualname(cls): text for cls, text in _REGISTRY.items()}


def is_registered(engine: object) -> bool:
    """Whether ``engine`` is an instance of a registered class."""
    return bool(_REGISTRY) and isinstance(engine, tuple(_REGISTRY))


def engine_result(  # noqa: PLR0913 - mirrors R's sas_engine_result()
    contract: Contract,
    status: str,
    *,
    outputs: dict[str, Any] | None = None,
    log: str = "",
    macros: dict[str, str] | None = None,
    sas_version: str = "",
    engine: str = "",
    run_id: str | None = None,
    started_at: datetime | str | None = None,
    ended_at: datetime | str | None = None,
) -> Result:
    """Build a run result for a registered engine (spec §6.6 (b), §8.4).

    The metadata holds the SHA-256 of the contract and program on disk,
    timestamps, the engine name, the package version as ``engine_version``, and
    the SAS version.

    Args:
        contract: The contract that was run.
        status: ``"success"``, ``"warning"`` or ``"error"`` (§6.5), from the SAS log.
        outputs: Output values (§8.1), keyed by output id.
        log: The full main-submission log text from SAS.
        macros: The rendered macro values (from :func:`sashiny.render_values`).
        sas_version: The SAS version (``&SYSVLONG``) of the run.
        engine: The engine name, for example ``"sas94-batch"``.
        run_id: The run identifier. Defaults to a generated UUID.
        started_at: Start time, a ``datetime`` or UTC ISO 8601 string (default: now).
        ended_at: End time, as ``started_at``.

    Returns:
        A :class:`sashiny.Result`.

    Raises:
        EngineError: For a status other than success, warning or error.

    """
    import uuid  # noqa: PLC0415 - keep import time low

    if status not in ("success", "warning", "error"):
        raise EngineError('status must be "success", "warning" or "error"')
    run_id = run_id or str(uuid.uuid4())
    result = Result.new(
        run_id,
        status,
        contract_sha256=contract_sha256(contract),
        program_sha256=program_sha256(contract),
        macros=dict(macros or {}),
        engine=engine,
        engine_version=__version__,
        sas_version=sas_version or "",
        started_at=started_at if isinstance(started_at, datetime) else None,
        ended_at=ended_at if isinstance(ended_at, datetime) else None,
    )
    if isinstance(started_at, str):
        result.metadata["started_at"] = started_at
    if isinstance(ended_at, str):
        result.metadata["ended_at"] = ended_at
    result.outputs = dict(outputs or {})
    result.log = log or ""
    return result
