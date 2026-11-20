"""Data frame accessors for run results (spec ``CONTRACT.md`` §8.7, non-normative).

The §8.1 values stay the cross-language wire format. These helpers turn them
into pandas data frames. pandas is an optional extra (``sashiny[frames]``), so it
is imported only when an accessor runs; the core imports without it.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from .collect import log_level, split_log
from .errors import ValuesError

if TYPE_CHECKING:
    from .result import Result

__all__ = ["frames", "log_frame", "table"]

_TYPES = {"error": "ERROR", "warning": "WARNING", "note": "NOTE", "text": "other"}


def _pandas() -> Any:
    try:
        import pandas as pd  # noqa: PLC0415 - optional extra
    except ImportError as exc:
        raise ImportError('result data frames need pandas: pip install "sashiny[frames]"') from exc
    return pd


def _is_table(value: Any) -> bool:
    return isinstance(value, dict) and "columns" in value and "rows" in value


def _is_log(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(v, dict) and "level" in v and "text" in v for v in value)
    )


def _output(result: Result, output_id: str) -> Any:
    if output_id not in result.outputs:
        raise KeyError(f"no output '{output_id}' in this result")
    value = result.outputs[output_id]
    if isinstance(value, dict) and set(value) == {"error"}:
        raise ValuesError(f"output '{output_id}' could not be collected: {value['error']}")
    return value


def _table_frame(value: dict[str, Any]) -> Any:
    pd = _pandas()
    numeric = [c["type"] == "numeric" and not value.get("formatted") for c in value["columns"]]
    data: dict[str, Any] = {}
    for j, col in enumerate(value["columns"]):
        cells = [row[j] for row in value["rows"]]
        if numeric[j]:
            data[col["name"]] = pd.Series(
                [math.nan if c is None else float(c) for c in cells], dtype="float64"
            )
        else:
            data[col["name"]] = pd.Series(
                [None if c is None else str(c) for c in cells], dtype="object"
            )
    df = pd.DataFrame(data, columns=[c["name"] for c in value["columns"]])
    df.attrs["labels"] = {c["name"]: c.get("label", "") for c in value["columns"]}
    df.attrs["formats"] = {c["name"]: c.get("format", "") for c in value["columns"]}
    df.attrs["total_rows"] = value.get("total_rows")
    df.attrs["truncated"] = bool(value.get("truncated"))
    return df


def _log_frame(text: list[str], types: list[str]) -> Any:
    pd = _pandas()
    return pd.DataFrame(
        {
            "line": pd.Series(range(1, len(text) + 1), dtype="int64"),
            "type": pd.Series(types, dtype="object"),
            "text": pd.Series(text, dtype="object"),
        }
    )


def table(result: Result, output_id: str) -> Any:
    """Return a ``table`` or ``chart`` output as a pandas DataFrame (spec §8.7).

    Args:
        result: The run result.
        output_id: The output id from the contract.

    Returns:
        A DataFrame. Labels and formats are in ``attrs["labels"]`` and
        ``attrs["formats"]``; ``attrs`` also has ``total_rows`` and ``truncated``.

    Raises:
        KeyError: If the result has no such output.
        ValueError: If the output is not a table or chart, or was not collected.
        ImportError: If pandas is not installed.

    """
    value = _output(result, output_id)
    if not _is_table(value):
        raise ValuesError(f"output '{output_id}' is not a table or chart")
    return _table_frame(value)


def log_frame(result: Result) -> Any:
    """Return the run's full log as a DataFrame with ``line``, ``type`` and ``text``."""
    lines = split_log(result.log or "")
    return _log_frame(lines, [_TYPES[log_level(line)] for line in lines])


def frames(result: Result) -> dict[str, Any]:
    """Return every output: tables and charts as DataFrames, logs as log frames, others as is."""
    out: dict[str, Any] = {}
    for oid, value in result.outputs.items():
        if _is_table(value):
            out[oid] = _table_frame(value)
        elif _is_log(value):
            out[oid] = _log_frame([v["text"] for v in value], [_TYPES[v["level"]] for v in value])
        else:
            out[oid] = value
    return out
