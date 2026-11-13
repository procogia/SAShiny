"""Advisory lint for SAShiny (spec §10).

Reports program-vs-contract consistency findings (``L001``-``L005``). These are
advisory, not errors. The implementation scans the SAS program text with
conservative, case-insensitive regular expressions; it deliberately avoids a
full SAS parser and prefers to miss a finding over raising a false positive.
"""

from __future__ import annotations

import re
from typing import Any

from .contract import Issue, all_macro_names

__all__ = ["lint"]

# A `%let NAME = ...;` assignment (NAME captured, case-insensitive).
_LET = re.compile(r"%let\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", re.IGNORECASE)

# A `call symput('NAME', ...)` or `call symputx('NAME', ...)` assignment.
_SYMPUT = re.compile(
    r"call\s+symputx?\s*\(\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]",
    re.IGNORECASE,
)

# A `%symexist(NAME)` guard reference.
_SYMEXIST = re.compile(r"%symexist\s*\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", re.IGNORECASE)


def _macro_reference(name: str) -> re.Pattern[str]:
    """Return a regex matching ``&NAME`` (case-insensitive), not ``&NAME_EXTRA``."""
    return re.compile(rf"&{re.escape(name)}\b", re.IGNORECASE)


def _assigned_names(program_text: str) -> set[str]:
    """Upper-cased macro names assigned via ``%let`` or ``call symput[x]``."""
    names: set[str] = set()
    for m in _LET.finditer(program_text):
        names.add(m.group(1).upper())
    for m in _SYMPUT.finditer(program_text):
        names.add(m.group(1).upper())
    return names


def _guarded_names(program_text: str) -> set[str]:
    """Upper-cased macro names referenced by a ``%symexist`` guard."""
    return {m.group(1).upper() for m in _SYMEXIST.finditer(program_text)}


def _dataset_targets(data: dict[str, Any]) -> set[str]:
    """Upper-cased WORK member names that dataset inputs target."""
    targets: set[str] = set()
    for spec in (data.get("inputs") or {}).values():
        if spec.get("type") == "dataset" and spec.get("target"):
            targets.add(spec["target"].upper())
    return targets


def _input_id_for_macro(data: dict[str, Any], name: str) -> str:
    """Return the input id that sets ``name``, or ``name`` lower-cased."""
    for iid, spec in (data.get("inputs") or {}).items():
        if name in all_macro_names({"inputs": {str(iid): spec}}):
            return str(iid)
    return name.lower()


def _lint_l001(
    data: dict[str, Any],
    text: str,
    injected: list[str],
    assigned: set[str],
    guarded: set[str],
) -> list[Issue]:
    """Return L001 findings: injected macro assigned outside a %symexist guard."""
    out: list[Issue] = []
    for name in injected:
        if name in assigned and name not in guarded:
            out.append(
                Issue(
                    "L001",
                    f"/inputs/{_input_id_for_macro(data, name)}",
                    f"macro {name} is assigned in the program outside a %symexist guard",
                )
            )
    return out


def _lint_l002(data: dict[str, Any], text: str, injected: list[str]) -> list[Issue]:
    """Return L002 findings: injected macro never referenced."""
    out: list[Issue] = []
    for name in injected:
        if not _macro_reference(name).search(text):
            out.append(
                Issue(
                    "L002",
                    f"/inputs/{_input_id_for_macro(data, name)}",
                    f"macro {name} is never referenced in the program",
                )
            )
    return out


def _lint_l003(data: dict[str, Any], text: str) -> list[Issue]:
    """Return L003 findings: `from` dataset never created and not a target."""
    out: list[Issue] = []
    targets = _dataset_targets(data)
    for oid, spec in (data.get("outputs") or {}).items():
        if spec.get("type") not in ("table", "download"):
            continue
        ref = spec.get("from")
        if not ref or "." not in ref:
            continue
        lib, member = ref.split(".", 1)
        if lib.upper() != "WORK":
            continue  # permanent library, not flagged
        if member.upper() in targets:
            continue
        if re.search(rf"\b{re.escape(member)}\b", text, re.IGNORECASE):
            continue
        out.append(
            Issue(
                "L003",
                f"/outputs/{oid}",
                f"dataset {ref} is never created in the program",
            )
        )
    return out


def _lint_l004(data: dict[str, Any]) -> list[Issue]:
    """Return L004 findings: more than one rtf/pdf download."""
    rtf_pdf = [
        oid
        for oid, spec in (data.get("outputs") or {}).items()
        if spec.get("type") == "download" and str(spec.get("format", "")).lower() in ("rtf", "pdf")
    ]
    if len(rtf_pdf) <= 1:
        return []
    return [
        Issue(
            "L004",
            "/outputs",
            "more than one rtf/pdf download; each receives the same output",
        )
    ]


def _lint_l005(data: dict[str, Any], text: str) -> list[Issue]:
    """Return L005 findings: `entry: macro` but `%macro` not found."""
    run = data.get("run") or {}
    if run.get("entry") != "macro":
        return []
    macro = run.get("macro")
    if macro and not re.search(rf"%macro\s+{re.escape(macro)}\b", text, re.IGNORECASE):
        return [Issue("L005", "/run/macro", f"%macro {macro} not found in the program")]
    return []


def lint(data: dict[str, Any], program_text: str) -> list[Issue]:
    """Return advisory lint findings for a contract and its program text.

    Args:
        data: The parsed contract data.
        program_text: The decoded SAS program text.

    Returns:
        A list of :class:`Issue` objects with ``L0xx`` codes. Empty when no
        findings are detected.

    """
    text = program_text or ""
    injected = all_macro_names(data)
    assigned = _assigned_names(text)
    guarded = _guarded_names(text)

    issues: list[Issue] = []
    issues.extend(_lint_l001(data, text, injected, assigned, guarded))
    issues.extend(_lint_l002(data, text, injected))
    issues.extend(_lint_l003(data, text))
    issues.extend(_lint_l004(data))
    issues.extend(_lint_l005(data, text))
    # A daterange or multichoice input sets several macro names that all map to
    # the same input id, so the same (code, path) can be reported more than once.
    # Deduplicate by (code, path) while preserving first-seen order.
    seen: set[tuple[str, str]] = set()
    deduped: list[Issue] = []
    for issue in issues:
        key = issue.key()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(issue)
    return deduped
