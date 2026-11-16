"""Generated SAS wrapper for SAShiny.

Implements ``spec/CONTRACT.md`` section 6: the reset submission and the
byte-exact main wrapper. The wrapper embeds the user's program text verbatim
and injects macro values only through single-quoted ``call symputx`` literals
followed by ``%superq``, and (``entry: macro``) call arguments with ``%nrstr``
masking where needed (spec §6.3).
"""

from __future__ import annotations

from typing import Any

from .contract import all_macro_names
from .values import superq_macros

__all__ = ["macro_arg", "reset_code", "wrapper_code"]

ODS_FORMATS = {"rtf", "pdf"}


def _quote_end(value: str, i: int) -> int:
    """Index of the quote closing the string that opens at ``value[i]``, or -1."""
    c, j = value[i], i + 1
    while (k := value.find(c, j)) != -1:
        if k + 1 < len(value) and value[k + 1] == c:
            j = k + 2
            continue
        return k
    return -1


def _mask(c: str) -> str:
    """Macro-quote one character outside a string literal (spec §6.3)."""
    if c == "%":
        return "%nrstr(%%)"
    if c in "'\"()":
        return f"%nrstr(%{c})"
    return f"%nrstr({c})"


def macro_arg(value: str) -> str:
    """Write a rendered value as a macro call argument (spec §6.3).

    Only the characters that would split the call or trigger macro execution
    are wrapped in ``%nrstr``: outside string literals ``,``, ``;``, ``&``,
    ``%`` and unmatched quotes or parentheses; inside double-quoted literals
    ``&`` and ``%``. Everything else, including whole single-quoted literals,
    is written as is, so SAS reads the value as ordinary program text (a
    macro-quoted value breaks ``WHERE`` clauses and names such as
    ``l&level``, see §9).
    """
    out: list[str] = []
    parens: list[int] = []
    i = 0
    while i < len(value):
        c = value[i]
        end = _quote_end(value, i) if c in "'\"" else -1
        if end != -1:
            seg = value[i : end + 1]
            if c == '"':
                seg = seg.replace("%", _mask("%")).replace("&", _mask("&"))
            out.append(seg)
            i = end + 1
            continue
        if c in "()":
            parens.append(len(out))
        out.append(_mask(c) if c in ",;&%'\"" else c)
        i += 1
    stack: list[int] = []
    unmatched: list[int] = []
    for idx in parens:
        if out[idx] == "(":
            stack.append(idx)
        elif stack:
            stack.pop()
        else:
            unmatched.append(idx)
    for idx in unmatched + stack:
        out[idx] = _mask(out[idx])
    return "".join(out)


def reset_code(data: dict[str, Any]) -> str:
    """Generate the reset submission (spec §6.2)."""
    lines = [
        "/* SAShiny 1 reset */",
        "proc datasets library=work kill nolist nowarn;",
        "quit;",
    ]
    names = all_macro_names(data)
    if names:
        lines.append(f"%symdel {' '.join(names)} / nowarn;")
    return "\n".join(lines) + "\n"


def wrapper_code(
    data: dict[str, Any],
    macros: dict[str, str],
    program_bytes: bytes,
    run_id: str = "fixture",
) -> str:
    """Generate the main wrapper submission (spec §6.3).

    Args:
        data: The parsed contract data.
        macros: Rendered macro values in spec §5.7 order.
        program_bytes: The raw bytes of the SAS program file.
        run_id: The run identifier embedded in the sentinel lines.

    Returns:
        The complete wrapper text, byte-for-byte per spec §6.3.

    """
    text = program_bytes.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    out = [
        "/* SAShiny 1 wrapper: generated, do not edit */",
        f"%put NOTE: SASHINY-BEGIN run={run_id};",
        "%let syscc = 0;",
    ]
    if macros:
        out.append("data _null_;")
        for name, value in macros.items():
            out.append(f"  call symputx('{name}', '{value.replace(chr(39), chr(39) * 2)}', 'G');")
        out.append("run;")
        needs_superq = superq_macros(data)
        for name in macros:
            if name in needs_superq:
                out.append(f"%let {name} = %superq({name});")
    ods = [
        (oid, spec["format"])
        for oid, spec in data["outputs"].items()
        if spec["type"] == "download" and spec["format"] in ODS_FORMATS
    ]
    for oid, fmt in ods:
        out.append(f'ods {fmt}(id={oid}) file="%sysfunc(pathname(work))/sashiny_{oid}.{fmt}";')
    out.append("%put NOTE: SASHINY-BEGIN-PROGRAM;")
    body = "\n".join(out) + "\n" + text
    tail: list[str] = []
    run = data.get("run") or {}
    if run.get("entry") == "macro":
        # With no macro variables the call is `%<MACRO>();` (spec §6.3).
        args = ", ".join(f"{n}={macro_arg(v)}" for n, v in macros.items())
        tail.append(f"%{run['macro']}({args});")
    tail.append("%put NOTE: SASHINY-END-PROGRAM;")
    tail.extend(f"ods {fmt}(id={oid}) close;" for oid, fmt in ods)
    tail.append(f"%put NOTE: SASHINY-END run={run_id} syscc=&syscc;")
    return body + "\n".join(tail) + "\n"
