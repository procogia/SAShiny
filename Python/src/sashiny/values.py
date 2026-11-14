"""Value validation and rendering for SAShiny.

Implements ``spec/CONTRACT.md`` sections 4-5: value validation (``V001``-``V014``)
and the rendering of validated values into the logical text of each macro
variable. Rendering is exact and specified; nothing here needs SAS-escaping
(that happens in :mod:`sashiny.wrapper`).
"""

from __future__ import annotations

import math
import re
from datetime import date
from typing import Any

from .contract import NUMERIC_LITERAL, SAS_NAME, Issue, choice_values, macro_names, resolve_date

__all__ = ["render_values", "superq_macros"]

SAS_EPOCH = date(1960, 1, 1)
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MAX_MACRO_BYTES = 32000
# Integers with absolute value below this are written without exponent (spec §5.1).
INTEGER_PLAIN_LIMIT = 1e15

# Unicode White_Space characters used for trimming text values (spec §4).
_WS = (
    "\t\n\x0b\x0c\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
    "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)


def superq_macros(data: dict[str, Any]) -> set[str]:
    """Return the macro names that need ``%superq`` (spec §6.3).

    Only ``raw`` text/choice values need macro quoting, because they are
    unquoted and could contain live ``&`` or ``%``. Quoted, dquoted, numeric,
    date, multichoice, dataset, and validated-bare values are already inert
    (SAS string literals or SAS names/numeric literals), so they are emitted
    directly and do not need ``%superq``.
    """
    out: set[str] = set()
    for iid, spec in (data.get("inputs") or {}).items():
        kind = spec["type"]
        if kind in ("text", "choice") and spec.get("render", "raw") == "raw":
            out.update(macro_names(iid, spec))
    return out


def render_number(x: float) -> str:
    """Render a numeric value per spec §5.1."""
    if x == 0:
        return "0"
    if float(x).is_integer() and abs(x) < INTEGER_PLAIN_LIMIT:
        return str(int(x))
    return f"{x:.15g}".replace("e", "E")


def render_text(v: str, mode: str) -> str:
    """Render a text/choice value per spec §5.2."""
    if mode == "quoted":
        return "'" + v.replace("'", "''") + "'"
    if mode == "dquoted":
        return '"' + v.replace('"', '""') + '"'
    return v


def render_date(dt: date, mode: str) -> str:
    """Render a date value per spec §5.4."""
    if mode == "date9":
        return f"{dt.day:02d}{MONTHS[dt.month - 1]}{dt.year:04d}"
    if mode == "iso":
        return dt.isoformat()
    if mode == "sasdate":
        return str((dt - SAS_EPOCH).days)
    return f"'{dt.day:02d}{MONTHS[dt.month - 1]}{dt.year:04d}'d"


def _ws_strip(v: str) -> str:
    return v.strip(_WS)


def render_values(  # noqa: PLR0912, PLR0913, PLR0917
    data: dict[str, Any],
    values: dict[str, Any],
    today: date,
    only: list[str] | None = None,
    choices_override: dict[str, list[str]] | None = None,
    uploads: dict[str, bool] | None = None,
) -> tuple[dict[str, str], list[Issue]]:
    """Validate and render values.

    Args:
        data: The parsed contract data.
        values: Input values keyed by input id, in JSON form (spec §2.1).
        today: The date used to resolve ``"today"``.
        only: When given, restrict processing to these input ids.
        choices_override: Choices read from SAS for ``choices_from`` inputs.
        uploads: Maps dataset input ids to ``True`` when a file was supplied.

    Returns:
        A tuple ``(macros, issues)`` where ``macros`` maps macro names (in
        spec §5.7 order) to their rendered text, and ``issues`` lists any
        validation errors.

    """
    inputs: dict[str, Any] = data.get("inputs") or {}
    uploads = uploads or {}
    macros: dict[str, str] = {}
    issues: list[Issue] = []
    if only is None:
        for k in values:
            if k not in inputs:
                issues.append(Issue("V011", k))
    for iid, spec in inputs.items():
        if only is not None and iid not in only:
            continue
        kind = spec["type"]
        names = macro_names(iid, spec)
        raw = values.get(iid)
        if kind == "dataset":
            present = bool(uploads.get(iid))
            if not present and not spec.get("optional", False):
                issues.append(Issue("V001", iid))
                continue
            for n in names:
                macros[n] = spec["target"].upper() if present else ""
            continue
        if isinstance(raw, str) and kind == "text":
            raw = _ws_strip(raw)
        optional = spec.get("optional", False)
        if kind == "multichoice" and raw == []:
            absent = optional
            if not optional and spec.get("min_selected", 1) >= 1:
                issues.append(Issue("V001", iid))
                continue
        else:
            absent = raw is None or raw == ""
            if absent and not optional:
                issues.append(Issue("V001", iid))
                continue
        if absent:
            for n in names:
                macros[n] = ""
            if kind == "multichoice" and "count_macro" in spec:
                macros[names[-1]] = "0"
            continue
        err, rendered = _render_one(iid, spec, raw, today, choices_override)
        if err:
            issues.append(err)
            continue
        for n, r in zip(names, rendered, strict=True):
            if len(r.encode("utf-8")) > MAX_MACRO_BYTES:
                issues.append(Issue("V013", iid))
                break
            macros[n] = r
    return macros, issues


def _render_one(  # noqa: PLR0911, PLR0912
    iid: str,
    spec: dict[str, Any],
    raw: Any,
    today: date,
    override: dict[str, list[str]] | None,
) -> tuple[Issue | None, list[str]]:
    kind = spec["type"]
    if kind == "numeric":
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return Issue("V002", iid), []
        if not math.isfinite(raw):
            return Issue("V003", iid), []
        if spec.get("integer") and not float(raw).is_integer():
            return Issue("V012", iid), []
        if ("min" in spec and raw < spec["min"]) or ("max" in spec and raw > spec["max"]):
            return Issue("V003", iid), []
        return None, [render_number(raw)]
    if kind == "text":
        if not isinstance(raw, str):
            return Issue("V002", iid), []
        if CONTROL.search(raw):
            return Issue("V007", iid), []
        if len(raw) > spec.get("max_length", 256):
            return Issue("V006", iid), []
        if "pattern" in spec and not re.fullmatch(spec["pattern"], raw, flags=re.ASCII):
            return Issue("V005", iid), []
        return None, [render_text(raw, spec.get("render", "raw"))]
    if kind == "choice":
        if not isinstance(raw, str):
            return Issue("V002", iid), []
        if CONTROL.search(raw):
            return Issue("V007", iid), []
        allowed = choice_values(spec) if "choices" in spec else (override or {}).get(iid)
        if allowed is not None and raw not in allowed:
            return Issue("V004", iid), []
        return None, [render_text(raw, spec.get("render", "raw"))]
    if kind == "multichoice":
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            return Issue("V002", iid), []
        if any(CONTROL.search(x) for x in raw):
            return Issue("V007", iid), []
        allowed = choice_values(spec) if "choices" in spec else (override or {}).get(iid)
        if allowed is not None and any(x not in allowed for x in raw):
            return Issue("V004", iid), []
        lo = spec.get("min_selected", 1)
        hi = spec.get("max_selected", len(raw))
        if len(set(raw)) != len(raw) or not (lo <= len(raw) <= hi):
            return Issue("V008", iid), []
        ordered = [c for c in allowed if c in raw] if allowed is not None else list(raw)
        mode = spec.get("render", "quoted")
        # Bare values are emitted unquoted (spec §6.3), so every selected
        # value must be a SAS name or numeric literal. Static choices are checked
        # by S007; dynamic choices_from values are checked here.
        if mode == "bare" and any(
            not (SAS_NAME.match(v) or NUMERIC_LITERAL.match(v)) for v in ordered
        ):
            return Issue("V004", iid), []
        parts = [v if mode == "bare" else render_text(v, mode) for v in ordered]

        sep = ", " if spec.get("separator", "space") == "comma" else " "
        out = [sep.join(parts)]
        if "count_macro" in spec:
            out.append(str(len(parts)))
        return None, out
    if kind in ("date", "daterange"):
        items = [raw] if kind == "date" else raw
        if kind == "daterange" and (not isinstance(raw, list) or len(raw) != 2):  # noqa: PLR2004
            return Issue("V002", iid), []
        # Type-check every element before any date validation (spec §4): a
        # non-string element is V002, never V009, even if another element is a
        # malformed date.
        if any(not isinstance(it, str) for it in items):
            return Issue("V002", iid), []
        dates: list[date] = []
        for it in items:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", it):
                    raise ValueError
                dt = resolve_date(it, today)
            except ValueError:
                return Issue("V009", iid), []
            if ("min" in spec and dt < resolve_date(spec["min"], today)) or (
                "max" in spec and dt > resolve_date(spec["max"], today)
            ):
                return Issue("V009", iid), []
            dates.append(dt)
        if kind == "daterange" and dates[0] > dates[1]:
            return Issue("V010", iid), []
        mode = spec.get("render", "literal")
        return None, [render_date(x, mode) for x in dates]
    raise AssertionError(kind)
