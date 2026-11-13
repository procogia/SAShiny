"""Result collection helpers (spec ``CONTRACT.md`` section 8).

Pure functions shared by the engines. They have no SAS dependency, so they are
unit-tested directly against the ``spec/fixtures/collect`` fixtures:

- log splitting, scoping and classification (§8.2 *log*);
- plot extraction from the ODS HTML document (§8.2 *plot*);
- the SAS code used to collect tables (§8.2 *table*);
- client-side download serialisation (§8.2 *download*);
- the recording key (§8.3).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import math
import re
from collections.abc import Iterable, Sequence
from typing import Any, Literal

__all__ = [
    "CSV_MAX_ROWS",
    "DOWNLOAD_MIME",
    "build_table",
    "choices_code",
    "csv_bytes",
    "download_value",
    "extract_plots",
    "formatted_table_code",
    "join_remote",
    "log_level",
    "recording_key",
    "recording_key_text",
    "scope_log",
    "select_columns",
    "split_log",
    "split_member",
    "table_meta_code",
    "xlsx_bytes",
    "xpt_bytes",
]

DOWNLOAD_MIME = {
    "csv": "text/csv",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xpt": "application/x-sas-xport",
    "sas7bdat": "application/x-sas-data",
    "rtf": "application/rtf",
    "pdf": "application/pdf",
}
CSV_MAX_ROWS = 1_000_000
XPT_V5_MAX_NAME = 8

# ASCII whitespace only (spec §8.1 "trailing blanks"): space, tab, CR, LF, VT, FF.
_ASCII_WS = " \t\n\r\f\v"

_LINE_BREAK = re.compile(r"\r\n|\r|\n")
_TRAILING_BREAK = re.compile(r"(\r\n|\r|\n)$")
_IMG = re.compile(
    r"""<img\b[^>]*?\bsrc\s*=\s*["']data:(image/[A-Za-z0-9.+-]+);base64,([^"']+)["']""",
    re.IGNORECASE,
)
_SVG = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)
_BEGIN = "NOTE: SASHINY-BEGIN-PROGRAM"
_END = "NOTE: SASHINY-END-PROGRAM"


# --------------------------------------------------------------------------- log


def split_log(log: str) -> list[str]:
    """Split a SAS log into lines (§8.2 *log*).

    Line breaks are CRLF, CR or LF. A trailing line break does not produce an
    empty final line. Trailing whitespace is removed from every line.

    Args:
        log: The raw log text.

    Returns:
        The log lines.

    """
    if not log:
        return []
    lines = _LINE_BREAK.split(log)
    if lines[-1] == "" and _TRAILING_BREAK.search(log):
        lines.pop()
    return [line.rstrip() for line in lines]


def log_level(line: str) -> str:
    """Classify one log line as ``error``, ``warning``, ``note`` or ``text``."""
    if line.startswith("ERROR"):
        return "error"
    if line.startswith("WARNING"):
        return "warning"
    if line.startswith("NOTE"):
        return "note"
    return "text"


def scope_log(log: str, scope: str = "program") -> list[dict[str, str]]:
    """Return the classified lines of a log output (§8.2 *log*).

    Args:
        log: The main-submission log.
        scope: ``"program"`` (between the program sentinels) or ``"full"``.

    Returns:
        A list of ``{"level", "text"}`` dicts.

    """
    lines = split_log(log)
    if scope == "program":
        if _BEGIN not in lines:
            return []
        rest = lines[lines.index(_BEGIN) + 1 :]
        lines = rest[: rest.index(_END)] if _END in rest else rest
    return [{"level": log_level(line), "text": line} for line in lines]


# --------------------------------------------------------------------------- plots


def extract_plots(html: str, select: int | None = None) -> list[dict[str, str]]:
    """Extract the ODS graphs embedded in an HTML document (§8.2 *plot*).

    Args:
        html: The ODS HTML document of the main submission.
        select: 1-based position of a single graph, or ``None`` for all.

    Returns:
        A list of ``{"mime", "data"}`` dicts (``data`` is base64).

    Raises:
        ValueError: If ``select`` exceeds the number of graphs found.

    """
    found: list[tuple[int, dict[str, str]]] = []
    for m in _IMG.finditer(html or ""):
        found.append((m.start(), {"mime": m.group(1).lower(), "data": m.group(2)}))
    for m in _SVG.finditer(html or ""):
        data = base64.b64encode(m.group(0).encode("utf-8")).decode("ascii")
        found.append((m.start(), {"mime": "image/svg+xml", "data": data}))
    plots = [plot for _, plot in sorted(found, key=lambda item: item[0])]
    if select is None:
        return plots
    if select < 1:
        raise ValueError(f"select={select} but graph positions are 1-based")
    if select > len(plots):
        raise ValueError(f"select={select} but the run produced {len(plots)} graph(s)")
    return [plots[select - 1]]


# --------------------------------------------------------------------------- tables


def split_member(ref: str) -> tuple[str, str]:
    """Split ``lib.member`` into upper-cased ``(LIB, MEM)``."""
    lib, mem = ref.split(".", 1)
    return lib.upper(), mem.upper()


def table_meta_code(lib: str, mem: str) -> str:
    """SAS code that reads column metadata and the row count (§8.2 *table* step 1)."""
    where = f'where libname = "{lib}" and memname = "{mem}"'
    lines = [
        "proc sql noprint;",
        "  create table work._sx_cols as",
        "    select varnum, name, type, format, label",
        "    from dictionary.columns",
        f"    {where}",
        "    order by varnum;",
        "  create table work._sx_nobs as",
        "    select nlobs from dictionary.tables",
        f"    {where};",
        "quit;",
    ]
    return "\n".join(lines) + "\n"


def choices_code(source: dict[str, Any]) -> str:
    """SAS code for a ``choices_from`` query (spec §6.4); names are schema-validated."""
    value = source["value_column"]
    label = source.get("label_column")
    cols = value if label is None else f"{value}, {label}"
    lines = [
        f"proc sql outobs={int(source.get('max_choices', 1000))} noprint;",
        "  create table work._sx_choices as",
        f"  select distinct {cols}",
        f"  from {source['dataset']}",
        f"  where not missing({value})",
        f"  order by {value};",
        "quit;",
    ]
    return "\n".join(lines) + "\n"


def formatted_table_code(lib: str, mem: str, columns: Sequence[str], max_rows: int) -> str:
    """SAS code that renders the selected columns as displayed strings (§8.2 *table* step 4)."""
    k = len(columns)
    lines = [
        "data work._sx_fmt;",
        f"  set {lib}.{mem}(obs={max_rows} keep={' '.join(columns)});",
        f"  length _sx_c1-_sx_c{k} $512;",
    ]
    lines += [f"  _sx_c{i} = strip(vvalue({col}));" for i, col in enumerate(columns, start=1)]
    lines += [f"  keep _sx_c1-_sx_c{k};", "run;"]
    return "\n".join(lines) + "\n"


def _clean_cell(value: Any, numeric: bool) -> Any:
    """Normalise one cell to its JSON form (§8.1)."""
    if value is None:
        return None
    if numeric:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if math.isnan(number):
            return None
        return int(number) if number.is_integer() and abs(number) < 2**53 else number
    if isinstance(value, float) and math.isnan(value):
        return ""
    return str(value).rstrip(_ASCII_WS)


def build_table(
    meta: Sequence[dict[str, Any]],
    rows: Iterable[Sequence[Any]],
    *,
    total_rows: int | None,
    max_rows: int,
    formatted: bool,
) -> dict[str, Any]:
    """Assemble a table output value (§8.1).

    Args:
        meta: Selected column metadata, each ``{"name", "type", "label", "format"}``.
        rows: Row values in column order.
        total_rows: Logical observation count, or ``None`` when unknown.
        max_rows: The contract's ``max_rows``.
        formatted: Whether cells are SAS-formatted strings.

    Returns:
        The table value.

    """
    numeric = [(not formatted) and m["type"] == "numeric" for m in meta]
    out_rows = []
    for row in rows:
        cells = [_clean_cell(v, n) for v, n in zip(row, numeric, strict=True)]
        if formatted:
            cells = ["" if c is None else str(c).strip(_ASCII_WS) for c in cells]
        out_rows.append(cells)
    return {
        "columns": [
            {
                "name": str(m["name"]),
                "type": m["type"],
                "label": str(m.get("label") or ""),
                "format": str(m.get("format") or ""),
            }
            for m in meta
        ],
        "rows": out_rows,
        "total_rows": total_rows,
        "truncated": total_rows is not None and total_rows > max_rows,
        "formatted": formatted,
    }


def select_columns(
    meta: Sequence[dict[str, Any]], wanted: Sequence[str] | None
) -> list[dict[str, Any]]:
    """Pick the contract's ``columns`` (case-insensitive, contract order) from metadata.

    Raises:
        ValueError: If a requested column does not exist.

    """
    if not wanted:
        return list(meta)
    by_name = {str(m["name"]).upper(): m for m in meta}
    missing = [c for c in wanted if c.upper() not in by_name]
    if missing:
        raise ValueError(f"column(s) not found: {', '.join(missing)}")
    return [by_name[c.upper()] for c in wanted]


# --------------------------------------------------------------------------- downloads


def join_remote(directory: str, name: str) -> str:
    r"""Join a remote SAS directory and file name (``\`` if the directory uses it)."""
    sep = "\\" if "\\" in directory else "/"
    return directory.rstrip("/\\") + sep + name


def csv_bytes(table: dict[str, Any]) -> bytes:
    """Serialise a raw table value to CSV (§8.2 *download*)."""
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([c["name"] for c in table["columns"]])
    for row in table["rows"]:
        writer.writerow(["" if v is None else v for v in row])
    return buf.getvalue().encode("utf-8")


def _dataframe(table: dict[str, Any]) -> Any:
    import pandas as pd  # noqa: PLC0415 - optional dependency

    return pd.DataFrame(table["rows"], columns=[c["name"] for c in table["columns"]])


def xlsx_bytes(table: dict[str, Any], sheet: str) -> bytes:
    """Serialise a raw table value to XLSX (needs ``pandas`` + ``openpyxl``)."""
    buf = io.BytesIO()
    _dataframe(table).to_excel(buf, sheet_name=sheet[:31], index=False)
    return buf.getvalue()


def xpt_bytes(table: dict[str, Any], member: str) -> bytes:
    """Serialise a raw table value to SAS transport (needs ``pyreadstat``).

    Uses version 5 when the member and all column names fit in 8 characters,
    otherwise version 8 (§8.2 *download*).
    """
    import tempfile  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    import pyreadstat  # noqa: PLC0415 - optional dependency

    names = [c["name"] for c in table["columns"]]
    version: Literal[5, 8] = (
        5 if len(member) <= XPT_V5_MAX_NAME and all(len(n) <= XPT_V5_MAX_NAME for n in names) else 8
    )
    labels = [c.get("label") or None for c in table["columns"]]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"{member.lower()}.xpt"
        pyreadstat.write_xport(
            _dataframe(table),
            str(path),
            table_name=member[:32],
            file_format_version=version,
            column_labels=labels,
        )
        return path.read_bytes()


def download_value(filename: str, fmt: str, data: bytes) -> dict[str, str]:
    """Build a download output value (§8.1)."""
    return {
        "filename": f"{filename}.{fmt}",
        "mime": DOWNLOAD_MIME[fmt],
        "data": base64.b64encode(data).decode("ascii"),
    }


# --------------------------------------------------------------------------- recordings


def recording_key_text(
    contract_sha256: str,
    macros: Iterable[tuple[str, str]],
    uploads: Iterable[tuple[str, str]],
) -> str:
    """Build the text whose SHA-256 is the recording key (§8.3)."""
    lines = ["sashiny-recording-key 1", f"contract {contract_sha256}"]
    lines += [f"macro {name}={value}" for name, value in macros]
    lines += [f"upload {iid} {digest}" for iid, digest in uploads]
    return "\n".join(lines) + "\n"


def recording_key(
    contract_sha256: str,
    macros: Iterable[tuple[str, str]],
    uploads: Iterable[tuple[str, str]],
) -> str:
    """Return the recording key (§8.3): hex SHA-256 of :func:`recording_key_text`."""
    text = recording_key_text(contract_sha256, macros, uploads)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
