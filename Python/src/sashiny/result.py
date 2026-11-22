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

__all__ = [
    "LogLine",
    "Result",
    "TableResult",
    "failure_reason",
    "output_summary",
    "utc_timestamp",
]


def utc_timestamp(when: datetime | None = None) -> str:
    """Return ``when`` (default: now) as ``YYYY-MM-DDTHH:MM:SSZ`` in UTC (spec §8.4).

    The one timestamp form both languages write, byte for byte (#156).
    """
    when = datetime.now(timezone.utc) if when is None else when.astimezone(timezone.utc)
    return when.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_utc(text: str) -> datetime:
    # Python 3.10's fromisoformat does not read a trailing "Z"; older results use "+00:00".
    return datetime.fromisoformat(text[:-1] + "+00:00" if text.endswith("Z") else text)


def first_error(log: str) -> tuple[int, str] | None:
    """Return ``(line number, text)`` of the first ``ERROR`` line, or ``None``."""
    from .collect import split_log  # noqa: PLC0415 - avoid an import cycle

    for i, line in enumerate(split_log(log or ""), 1):
        if line.startswith("ERROR"):
            return i, line
    return None


def failure_reason(result: Result) -> str:
    """Return the first reason a run failed: ERROR line, engine error or invalid input."""
    hit = first_error(result.log)
    if hit is not None:
        return f"{hit[1]} (log line {hit[0]})"
    meta = result.metadata
    if meta.get("engine_error"):
        return str(meta["engine_error"])
    issues = meta.get("issues") or []
    if issues:
        i = issues[0]
        parts = ["invalid input", i.get("code", ""), i.get("input") or "", i.get("message") or ""]
        return " ".join(p for p in parts if p)
    return "no ERROR line in the log"


def _duration(started: Any, ended: Any) -> float | None:
    try:
        return (_parse_utc(ended) - _parse_utc(started)).total_seconds()
    except (TypeError, ValueError):
        return None


def output_summary(value: Any) -> str:  # noqa: PLR0911 - one return per output kind
    """Return a one-line summary of a §8.1 output value."""
    if isinstance(value, dict) and set(value) == {"error"}:
        return f"not collected: {value['error']}"
    if isinstance(value, dict) and "columns" in value and "rows" in value:
        n, total = len(value["rows"]), value.get("total_rows")
        more = f" of {total}" if total is not None and total > n else ""
        return f"table, {n} row(s){more} x {len(value['columns'])} column(s)"
    if (
        isinstance(value, list)
        and value
        and all(isinstance(v, dict) and "level" in v for v in value)
    ):
        return f"log, {len(value)} line(s)"
    if isinstance(value, dict) and "sas" in value and "sashiny" in value:
        return "paired SAS graph and SAShiny chart"
    if isinstance(value, dict) and "filename" in value:
        return f"download {value['filename']}"
    if isinstance(value, str):
        return f"html, {len(value)} characters"
    if isinstance(value, list):
        return f"plot, {len(value)} graph(s)"
    return type(value).__name__


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

    def check(self) -> Result:
        """Return ``self`` if the run succeeded or warned; otherwise raise :class:`RunError`.

        The message names the run id and the first ``ERROR`` log line (or the
        engine error, or the first invalid input), like R's ``sas_check()``.

        Raises:
            RunError: If ``status`` is ``error`` (or anything but success/warning).

        """
        if self.status in ("success", "warning"):
            return self
        from .errors import RunError  # noqa: PLC0415 - avoid an import cycle

        raise RunError(f"run {self.run_id} failed: {failure_reason(self)}", self)

    def __repr__(self) -> str:
        """Status, run id, duration, backend, failure reason and one line per output."""
        meta = self.metadata
        lines = [f"<sashiny result> {self.status}", f"  run id:   {self.run_id}"]
        seconds = meta.get("seconds", _duration(meta.get("started_at"), meta.get("ended_at")))
        if seconds is not None:
            lines.append(f"  duration: {float(seconds):.2f} s")
        lines.append(f"  backend:  {meta.get('backend') or meta.get('engine', '')}")
        if self.status not in ("success", "warning"):
            lines.append(f"  reason:   {failure_reason(self)}")
        if self.outputs:
            lines.append("  outputs:")
            lines += [f"    {k}: {output_summary(v)}" for k, v in self.outputs.items()]
        return "\n".join(lines)

    def table(self, output_id: str) -> Any:
        """Return a table or chart output as a pandas DataFrame (spec §8.7).

        Needs pandas (``pip install "sashiny[frames]"``). See :func:`sashiny.frames.table`.
        """
        from .frames import table  # noqa: PLC0415 - keeps pandas optional

        return table(self, output_id)

    def log_frame(self) -> Any:
        """Return the full log as a DataFrame with ``line``, ``type`` and ``text`` (spec §8.7)."""
        from .frames import log_frame  # noqa: PLC0415 - keeps pandas optional

        return log_frame(self)

    def frames(self) -> dict[str, Any]:
        """Return every output, with tables and logs as DataFrames (spec §8.7)."""
        from .frames import frames  # noqa: PLC0415 - keeps pandas optional

        return frames(self)

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
        return cls(
            run_id=run_id,
            status=status,
            metadata={
                "run_id": run_id,
                "contract_sha256": contract_sha256,
                "program_sha256": program_sha256,
                "macros": macros or {},
                "started_at": utc_timestamp(started_at),
                "ended_at": utc_timestamp(ended_at),
                "engine": engine,
                "engine_version": engine_version,
                "sas_version": sas_version,
                "status": status,
                "collect_errors": [],
            },
        )
