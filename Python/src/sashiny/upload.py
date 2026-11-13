"""Dataset upload conversion (spec ``CONTRACT.md`` section 7).

Reads an uploaded file (or a contract's ``sample``) into a pandas data frame
ready for ``saspy.SASsession.df2sd``: column names sanitised, declared columns
type-converted, and dates marked for conversion to SAS dates.

Requires the ``upload`` extra (``pandas``; ``openpyxl`` for ``xlsx``;
``pyreadstat`` for ``xpt`` / ``sas7bdat``, with a ``pandas.read_sas`` fallback).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "UploadError",
    "UploadFile",
    "file_sha256",
    "read_upload",
    "resolve_upload",
    "sanitize_names",
]

_INVALID = re.compile(r"[^A-Za-z0-9_]")
MAX_NAME_BYTES = 32
BYTES_PER_MB = 1024 * 1024


class UploadError(ValueError):
    """An upload failed §7 conversion (reported as ``V014``)."""


@dataclass(frozen=True)
class UploadFile:
    """A file supplied for a dataset input.

    Attributes:
        path: Where the file is on disk.
        name: The original file name (its extension selects the reader).

    """

    path: Path
    name: str

    @property
    def extension(self) -> str:
        """Lower-case extension without the dot."""
        return Path(self.name).suffix.lower().lstrip(".")


def resolve_upload(value: Any, spec: dict[str, Any], base_dir: Path) -> UploadFile | None:
    """Turn an ``uploads`` entry into an :class:`UploadFile`.

    ``True`` selects the contract's ``sample`` file. A path or
    :class:`UploadFile` selects that file. Falsy values mean "not supplied".
    """
    if not value:
        return None
    if value is True:
        if "sample" not in spec:
            raise UploadError("no file supplied and the input has no sample")
        path = base_dir / spec["sample"]
        return UploadFile(path=path, name=path.name)
    if isinstance(value, UploadFile):
        return value
    path = Path(value)
    return UploadFile(path=path, name=path.name)


def file_sha256(path: Path) -> str:
    """SHA-256 of a file's bytes (used in the recording key, §8.3)."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sanitize_names(names: list[str]) -> list[str]:
    """Sanitise column names (§7 step 2).

    Characters outside ``[A-Za-z0-9_]`` become ``_``; a leading digit gets a
    ``_`` prefix; names are truncated to 32 bytes; case-insensitive duplicates
    get ``_2``, ``_3``, ... suffixes (truncating further to fit).
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = _INVALID.sub("_", str(raw)) or "_"
        if name[0].isdigit():
            name = "_" + name
        name = name[:MAX_NAME_BYTES]
        candidate, n = name, 1
        while candidate.upper() in seen:
            n += 1
            suffix = f"_{n}"
            candidate = name[: MAX_NAME_BYTES - len(suffix)] + suffix
        seen.add(candidate.upper())
        out.append(candidate)
    return out


def _read(upload: UploadFile) -> tuple[Any, bool]:
    """Read the file; returns (data frame, all_text) where all_text marks CSV input."""
    import pandas as pd  # noqa: PLC0415 - optional dependency

    ext = upload.extension
    if ext == "csv":
        # Read with header=None so duplicate header names survive verbatim
        # (pandas otherwise mangles "x,x" to "x,x.1" before §7 step 2 can
        # resolve them to "x","x_2"). The first row is the header; sanitise it
        # before assigning so the frame never holds duplicate column names.
        raw = pd.read_csv(
            upload.path, header=None, dtype=str, keep_default_na=False, encoding="utf-8"
        )
        header = [str(c) for c in raw.iloc[0].tolist()]
        df = raw.iloc[1:].reset_index(drop=True)
        df.columns = sanitize_names(header)
        return df, True
    if ext == "xlsx":
        # keep_default_na=False preserves literal "NA"/"nan"/"None" text and
        # leading-zero strings (spec §7 step 3: only empty/whitespace is missing;
        # any other non-conforming text is unparseable V014). Native numeric and
        # date cell types are still inferred for undeclared columns (§7 step 4).
        return pd.read_excel(upload.path, sheet_name=0, keep_default_na=False), False
    if ext in ("xpt", "sas7bdat"):
        try:
            import pyreadstat  # noqa: PLC0415

            reader = pyreadstat.read_xport if ext == "xpt" else pyreadstat.read_sas7bdat
            df, _meta = reader(str(upload.path))
        except ImportError:
            df = pd.read_sas(
                upload.path, format="xport" if ext == "xpt" else "sas7bdat", encoding="utf-8"
            )
        return df, False
    raise UploadError(f"unsupported file type .{ext}")


def _check_file(upload: UploadFile, spec: dict[str, Any]) -> None:
    """Check extension, existence and size (§7 step 1)."""
    accept = spec.get("accept", ["csv", "xlsx", "xpt", "sas7bdat"])
    if upload.extension not in accept:
        raise UploadError(f".{upload.extension} is not accepted (accepted: {', '.join(accept)})")
    if not upload.path.is_file():
        raise UploadError(f"file not found: {upload.name}")
    limit = spec.get("max_size_mb", 50)
    size_mb = upload.path.stat().st_size / BYTES_PER_MB
    if size_mb > limit:
        raise UploadError(f"{upload.name} is {size_mb:.1f} MB (limit {limit} MB)")


def _to_numeric(series: Any, name: str, all_text: bool) -> Any:
    import pandas as pd  # noqa: PLC0415 - optional dependency

    blank = series.astype(str).str.strip() == "" if all_text else series.isna()
    if not all_text:
        # Non-CSV readers may leave whitespace-only cells as strings; treat them
        # as empty (spec §7 step 3 "empty = missing").
        blank = blank | (series.astype(str).str.strip() == "")
    converted = pd.to_numeric(series.where(~blank), errors="coerce")
    if (converted.isna() & ~blank & series.notna()).any():
        raise UploadError(f"column {name} has values that are not numbers")
    return converted


def _to_date(series: Any, name: str) -> Any:
    import pandas as pd  # noqa: PLC0415 - optional dependency

    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    text = series.astype(str).str.strip()
    # Only native missing and empty/whitespace are "missing" (spec §7 step 3);
    # any other non-ISO text (including the literal "NA", "nan", "NaT", "None")
    # is unparseable and reported as V014.
    blank = series.isna() | (text == "")
    # Enforce the exact ISO shape (spec §7 step 3): pandas' "%Y-%m-%d" format
    # accepts non-zero-padded fields such as "2026-1-2", which R rejects.
    shape_ok = text.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False)
    parsed = pd.to_datetime(text.where(~blank & shape_ok), format="%Y-%m-%d", errors="coerce")
    if (parsed.isna() & ~blank).any():
        raise UploadError(f"column {name} has values that are not YYYY-MM-DD dates")
    return parsed


def _to_character(series: Any) -> Any:
    """Convert a declared character column to strings (spec §7 step 3).

    Integer-valued floats render without a trailing ``.0`` (``1.0`` -> ``"1"``),
    matching R's ``as.character``. Native missing values become ``""``.
    """

    def _fmt(v: Any) -> str:
        if isinstance(v, float) and v.is_integer():
            return str(int(v))
        return str(v)

    return series.where(series.notna(), "").map(_fmt)


def _infer_csv_numbers(df: Any, declared: set[str]) -> None:
    """§7 step 4: undeclared CSV columns that are all numbers become numeric."""
    import pandas as pd  # noqa: PLC0415 - optional dependency

    for name in df.columns:
        if name in declared:
            continue
        text = df[name].str.strip()
        nonblank = text != ""
        converted = pd.to_numeric(text.where(nonblank), errors="coerce")
        if nonblank.any() and not (converted.isna() & nonblank).any():
            df[name] = converted


def read_upload(upload: UploadFile, spec: dict[str, Any]) -> tuple[Any, dict[str, str]]:
    """Read and convert an upload per §7.

    Args:
        upload: The supplied file.
        spec: The contract's dataset input spec.

    Returns:
        ``(data_frame, datetimes)`` where ``datetimes`` maps date columns to
        ``"date"`` for ``df2sd``.

    Raises:
        UploadError: Wrong extension, too large, unreadable, a missing declared
            column, or an unparseable declared value (all ``V014``).

    """
    _check_file(upload, spec)
    try:
        df, all_text = _read(upload)
    except UploadError:
        raise
    except Exception as exc:
        raise UploadError(f"could not read {upload.name}: {exc}") from exc

    df.columns = sanitize_names([str(c) for c in df.columns])
    by_upper = {c.upper(): c for c in df.columns}
    datetimes: dict[str, str] = {}
    declared: set[str] = set()
    for col in spec.get("columns", []):
        name = by_upper.get(col["name"].upper())
        if name is None:
            raise UploadError(f"{upload.name} has no column {col['name']}")
        declared.add(name)
        series = df[name]
        if col["type"] == "numeric":
            df[name] = _to_numeric(series, name, all_text)
        elif col["type"] == "date":
            df[name] = _to_date(series, name)
            datetimes[name] = "date"
        else:
            df[name] = _to_character(series)
    if all_text:
        _infer_csv_numbers(df, declared)
    return df, datetimes
