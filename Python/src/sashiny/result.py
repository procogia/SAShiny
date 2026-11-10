"""Run result object for SAShiny.

Implements ``spec/CONTRACT.md`` section 8: the collected outputs of a run plus
its metadata. A :class:`Result` is produced by an engine's ``run`` method and
carries the run metadata required by the spec (run_id, contract/program hashes,
rendered macros, timestamps, engine/SAS version, status).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

__all__ = ["LogLine", "Result", "TableResult"]


@dataclass
class LogLine:
    """A classified log line (kept for compatibility; outputs use §8.1 dicts)."""

    text: str
    level: str  # "error" | "warning" | "note" | "text"


@dataclass
class TableResult:
    """A collected table (kept for compatibility; outputs use §8.1 dicts)."""

    columns: list[str]
    rows: list[list[Any]]
    truncated: bool = False
    total_rows: int = 0


@dataclass
class Result:
    """The collected outputs and metadata of a single run.

    Attributes:
        run_id: The run identifier (spec §6.1).
        status: ``success`` | ``warning`` | ``error`` (spec §6.5).
        outputs: Collected outputs keyed by output id. Each value is the
            language-neutral JSON value of spec §8.1 (tables, plots, HTML, log
            lines and base64 downloads as dicts, lists and strings), or
            ``{"error": message}`` when that output could not be collected.
        log: The full main-submission log text.
        metadata: Run metadata (contract/program hashes, rendered macros,
            timestamps, engine/SAS version).

    """

    run_id: str
    status: str
    outputs: dict[str, Any] = field(default_factory=dict)
    log: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def new(  # noqa: PLR0913 - many optional metadata fields
        cls,
        run_id: str,
        status: str,
        *,
        contract_sha256: str = "",
        program_sha256: str = "",
        macros: dict[str, str] | None = None,
        engine: str = "",
        engine_version: str = "",
        sas_version: str = "",
        started_at: datetime | None = None,
        ended_at: datetime | None = None,
    ) -> Result:
        """Construct a :class:`Result` with the standard metadata fields."""
        started_at = started_at or datetime.now(timezone.utc)
        ended_at = ended_at or datetime.now(timezone.utc)
        return cls(
            run_id=run_id,
            status=status,
            metadata={
                "run_id": run_id,
                "contract_sha256": contract_sha256,
                "program_sha256": program_sha256,
                "macros": macros or {},
                "started_at": started_at.isoformat(),
                "ended_at": ended_at.isoformat(),
                "engine": engine,
                "engine_version": engine_version,
                "sas_version": sas_version,
                "status": status,
                "collect_errors": [],
            },
        )
