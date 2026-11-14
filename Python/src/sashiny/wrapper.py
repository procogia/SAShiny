"""Generated SAS wrapper for SAShiny.

Implements ``spec/CONTRACT.md`` section 6: the reset submission and the
byte-exact main wrapper. The wrapper embeds the user's program text verbatim
and injects macro values only through single-quoted ``call symputx`` literals
followed by ``%superq`` (spec §6.3).
"""

from __future__ import annotations

from typing import Any

from .contract import all_macro_names
from .values import superq_macros

__all__ = ["reset_code", "wrapper_code"]

ODS_FORMATS = {"rtf", "pdf"}


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
        # With no macro variables the call is `%<MACRO>();` (spec §6.3). An empty
        # join would otherwise emit `%<MACRO>(=%bquote(&));`.
        args = ", ".join(f"{n}=%bquote(&{n})" for n in macros)
        tail.append(f"%{run['macro']}({args});")
    tail.append("%put NOTE: SASHINY-END-PROGRAM;")
    tail.extend(f"ods {fmt}(id={oid}) close;" for oid, fmt in ods)
    tail.append(f"%put NOTE: SASHINY-END run={run_id} syscc=&syscc;")
    return body + "\n".join(tail) + "\n"
