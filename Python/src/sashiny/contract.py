"""Contract loading and validation for SAShiny.

Implements ``spec/CONTRACT.md`` sections 1-3: safe YAML loading (no timestamp
typing), JSON Schema 2020-12 validation (``E000``) and the semantic rules
``S001``-``S016``. Every error is reported with a ``code``, a JSON-pointer-style
``path`` and a message.

This module is the shipped equivalent of the reference oracle
``spec/tools/sashiny_ref.py`` and must behave identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from ._schema import SCHEMA

__all__ = ["Contract", "Issue", "load", "validate"]

# Reserved macro-name prefixes (spec §3.2 S002).
RESERVED = re.compile(r"^(SYS|SASHINY|_SX_)", re.IGNORECASE)
SAS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
NUMERIC_LITERAL = re.compile(r"^-?(\d+\.?\d*|\.\d+)([Ee][+-]?\d+)?$")

# Portable regex subset (spec §3.3): reject constructs outside the subset.
_FORBIDDEN_REGEX = [
    (re.compile(r"\(\?[=!<]"), "look-around"),
    (re.compile(r"\(\?P?<"), "named group"),
    (re.compile(r"\(\?[a-zA-Z]"), "inline flag"),
    (re.compile(r"\\[1-9]"), "back-reference"),
    (re.compile(r"\\[pPkK]"), "unicode property / named back-reference"),
    (re.compile(r"[*+?}]\?"), "lazy quantifier"),
    (re.compile(r"[*+?}]\+"), "possessive quantifier"),
    (re.compile(r"(?<!\\)[\^$]"), "anchor"),
]


class SafeLoaderNoDates(yaml.SafeLoader):  # type: ignore[misc]
    """Safe loader that keeps ISO dates as strings (spec §1.1)."""


SafeLoaderNoDates.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"]
    for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@dataclass
class Issue:
    """A single validation error.

    Attributes:
        code: Error code (``E000``, ``S001``-``S016``).
        path: JSON-pointer-style path to the offending value.
        message: Human-readable detail.

    """

    code: str
    path: str
    message: str = ""

    def key(self) -> tuple[str, str]:
        """Return the ``(code, path)`` pair used for fixture comparison."""
        return (self.code, self.path)


@dataclass
class Contract:
    """A loaded contract: its parsed data and the directory it lives in."""

    data: dict[str, Any]
    base_dir: Path
    issues: list[Issue] = field(default_factory=list)
    path: Path | None = None


def load(path: str | Path) -> Contract:
    """Load a contract YAML file with a safe loader.

    Args:
        path: Path to the ``*.sashiny.yml`` file.

    Returns:
        A :class:`Contract` holding the parsed data and the file's directory.

    """
    p = Path(path)
    data = yaml.load(p.read_text(encoding="utf-8"), Loader=SafeLoaderNoDates)  # noqa: S506
    return Contract(data=data, base_dir=p.parent, path=p)


def validate(contract: Contract, today: date | None = None) -> list[Issue]:
    """Validate a contract, returning every schema and semantic issue.

    Args:
        contract: The loaded :class:`Contract`.
        today: The date used to resolve ``"today"`` in date bounds. Defaults to
            the current date.

    Returns:
        A list of :class:`Issue` objects. Empty when the contract is valid.

    """
    issues: list[Issue] = []
    validator = Draft202012Validator(SCHEMA)
    for err in validator.iter_errors(contract.data):
        pointer = "/" + "/".join(str(p) for p in err.absolute_path)
        issues.append(Issue("E000", pointer if pointer != "/" else "", err.message))
    if issues:
        # Semantic checks assume a structurally valid document.
        return issues
    issues.extend(_semantic(contract, today or date.today()))
    return issues


# --------------------------------------------------------------------------- helpers


def macro_names(input_id: str, spec: dict[str, Any]) -> list[str]:
    """Macro names set by one input, upper-cased, in spec §5.7 order."""
    kind = spec["type"]
    if kind == "dataset":
        return [spec["macro"].upper()] if "macro" in spec else []
    if kind == "daterange":
        names = spec.get("macro", [f"{input_id}_start", f"{input_id}_end"])
        return [n.upper() for n in names]
    names = [spec.get("macro", input_id).upper()]
    if kind == "multichoice" and "count_macro" in spec:
        names.append(spec["count_macro"].upper())
    return names


def all_macro_names(data: dict[str, Any]) -> list[str]:
    """All macro names a contract can set, in contract order."""
    out: list[str] = []
    for iid, spec in (data.get("inputs") or {}).items():
        out.extend(macro_names(iid, spec))
    return out


def choice_values(spec: dict[str, Any]) -> list[str] | None:
    """Return the static choice values, or ``None`` when ``choices_from`` is used."""
    if "choices" not in spec:
        return None
    return [c if isinstance(c, str) else c["value"] for c in spec["choices"]]


def resolve_date(value: str, today: date) -> date:
    """Resolve a date value, mapping ``"today"`` to ``today``."""
    return today if value == "today" else date.fromisoformat(value)


def _is_int(x: Any) -> bool:
    return (isinstance(x, int) and not isinstance(x, bool)) or (
        isinstance(x, float) and x.is_integer()
    )


def _check_regex(pattern: str) -> str | None:
    for rx, what in _FORBIDDEN_REGEX:
        if rx.search(pattern):
            return what
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"does not compile: {exc}"
    return None


# --------------------------------------------------------------------------- semantic layer


def _semantic(contract: Contract, today: date) -> list[Issue]:  # noqa: PLR0912, PLR0915
    d = contract.data
    inputs: dict[str, Any] = d.get("inputs") or {}
    outputs: dict[str, Any] = d["outputs"]
    issues: list[Issue] = []

    # S001 / S002
    seen: dict[str, str] = {}
    for iid, spec in inputs.items():
        for name in macro_names(iid, spec):
            if name in seen:
                issues.append(
                    Issue("S001", f"/inputs/{iid}", f"macro {name} also set by {seen[name]}")
                )
            else:
                seen[name] = iid
        explicit = spec.get("macro") is not None
        if spec["type"] not in ("dataset", "daterange") and not explicit and RESERVED.match(iid):
            issues.append(Issue("S002", f"/inputs/{iid}", "default macro name is reserved"))
        if spec["type"] == "daterange" and not explicit and RESERVED.match(iid):
            issues.append(Issue("S002", f"/inputs/{iid}", "default macro names are reserved"))

    for iid, spec in inputs.items():
        p = f"/inputs/{iid}"
        kind = spec["type"]
        # S003
        if kind == "numeric" and "min" in spec and "max" in spec and spec["min"] > spec["max"]:
            issues.append(Issue("S003", p, "min > max"))
        if (
            kind in ("date", "daterange")
            and "min" in spec
            and "max" in spec
            and resolve_date(spec["min"], today) > resolve_date(spec["max"], today)
        ):
            issues.append(Issue("S003", p, "min > max"))
        # S005
        vals = choice_values(spec)
        if vals is not None and len(set(vals)) != len(vals):
            issues.append(Issue("S005", f"{p}/choices", "duplicate choice values"))
        # S006
        if kind == "multichoice":
            lo = spec.get("min_selected", 1)
            hi = spec.get("max_selected")
            if hi is not None and lo > hi:
                issues.append(Issue("S006", p, "min_selected > max_selected"))
            if vals is not None and (lo > len(vals) or (hi is not None and hi > len(vals))):
                issues.append(Issue("S006", p, "selection bounds exceed number of choices"))
            # S007
            bad_bare = vals is not None and any(
                not (SAS_NAME.match(v) or NUMERIC_LITERAL.match(v)) for v in vals
            )
            if spec.get("render") == "bare" and bad_bare:
                issues.append(
                    Issue("S007", f"{p}/choices", "bare render needs SAS names or numbers")
                )
        # S014
        if kind == "text" and "pattern" in spec:
            problem = _check_regex(spec["pattern"])
            if problem:
                issues.append(Issue("S014", f"{p}/pattern", problem))
        # S015
        if kind == "numeric" and spec.get("integer"):
            for k in ("min", "max", "default"):
                if k in spec and not _is_int(spec[k]):
                    issues.append(Issue("S015", f"{p}/{k}", "must be an integer"))
        # S016
        if kind == "dataset" and "columns" in spec:
            names = [c["name"].upper() for c in spec["columns"]]
            if len(set(names)) != len(names):
                issues.append(Issue("S016", f"{p}/columns", "duplicate column names"))
        # S013 (sample)
        if (
            kind == "dataset"
            and "sample" in spec
            and not (contract.base_dir / spec["sample"]).is_file()
        ):
            issues.append(Issue("S013", f"{p}/sample", "sample file not found"))
        # S004
        if "default" in spec and kind != "dataset":
            default = spec["default"]
            if kind in ("date", "daterange"):
                iso = today.isoformat()
                if isinstance(default, list):
                    default = [iso if x == "today" else x for x in default]
                elif default == "today":
                    default = iso
            _, errs = _render_values_for_default(d, {iid: default}, today, only=[iid])
            for e in errs:
                issues.append(Issue("S004", f"{p}/default", e.code))

    # S008
    for oid, spec in outputs.items():
        if spec["type"] == "download":
            if spec["format"] in DATA_FORMATS and "from" not in spec:
                issues.append(Issue("S008", f"/outputs/{oid}", "data download needs 'from'"))
            if spec["format"] in ODS_FORMATS and "from" in spec:
                issues.append(Issue("S008", f"/outputs/{oid}", "ODS download must not have 'from'"))
    # S009
    run = d.get("run") or {}
    if run.get("entry") == "macro" and "macro" not in run:
        issues.append(Issue("S009", "/run", "entry: macro requires run.macro"))
    if "macro" in run and run.get("entry") != "macro":
        issues.append(Issue("S009", "/run/macro", "run.macro requires entry: macro"))
    # S010
    targets: dict[str, str] = {}
    for iid, spec in inputs.items():
        if spec["type"] == "dataset":
            t = spec["target"].upper()
            if t in targets:
                issues.append(
                    Issue("S010", f"/inputs/{iid}/target", f"target also used by {targets[t]}")
                )
            targets[t] = iid
    # S011
    for oid in outputs:
        if oid in inputs:
            issues.append(Issue("S011", f"/outputs/{oid}", "id collides with an input id"))
    # S012
    for i, ref in enumerate((d.get("ui") or {}).get("order", [])):
        if ref not in inputs:
            issues.append(Issue("S012", f"/ui/order/{i}", f"unknown input {ref}"))
    # S013 (program)
    if not (contract.base_dir / d["program"]).is_file():
        issues.append(Issue("S013", "/program", "program file not found"))
    return issues


# Imported lazily to avoid a circular import with values.py.
DATA_FORMATS = {"csv", "xlsx", "xpt", "sas7bdat"}
ODS_FORMATS = {"rtf", "pdf"}


def _render_values_for_default(
    data: dict[str, Any],
    values: dict[str, Any],
    today: date,
    only: list[str] | None = None,
) -> tuple[dict[str, str], list[Issue]]:
    """Validate a default value via the value renderer (spec §3.2 S004)."""
    from .values import render_values  # noqa: PLC0415 - circular import with values.py

    return render_values(data, values, today, only=only)
