"""Reference oracle for the SAShiny contract specification (version 1).

This module is a deliberately small, dependency-light implementation of
``spec/CONTRACT.md``. It exists only to keep the shared fixtures internally
consistent while the R and Python packages are being built. It is not the
Python library (that lives in ``Python/src/sashiny``) and is never shipped.

Sections referenced in comments (e.g. "5.3") point to CONTRACT.md.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

SPEC_DIR = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((SPEC_DIR / "sashiny.schema.json").read_text(encoding="utf-8"))
SAS_EPOCH = date(1960, 1, 1)
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
RESERVED = re.compile(r"^(SYS|SASHINY|_SX_)", re.IGNORECASE)
SAS_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,31}$")
NUMERIC_LITERAL = re.compile(r"^-?(\d+\.?\d*|\.\d+)([Ee][+-]?\d+)?$")
CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MAX_MACRO_BYTES = 32000
DATA_FORMATS = {"csv", "xlsx", "xpt", "sas7bdat"}
ODS_FORMATS = {"rtf", "pdf"}

# Portable regex subset (3.3): reject constructs outside the subset.
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


class SafeLoaderNoDates(yaml.SafeLoader):
    """Safe loader that keeps ISO dates as strings (1.1)."""


SafeLoaderNoDates.yaml_implicit_resolvers = {
    k: [(tag, rx) for tag, rx in v if tag != "tag:yaml.org,2002:timestamp"] for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


@dataclass
class Issue:
    code: str
    path: str
    message: str = ""

    def key(self) -> tuple[str, str]:
        return (self.code, self.path)


@dataclass
class Contract:
    data: dict[str, Any]
    base_dir: Path
    issues: list[Issue] = field(default_factory=list)


# --------------------------------------------------------------------------- loading


def load(path: Path) -> Contract:
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=SafeLoaderNoDates)  # noqa: S506
    return Contract(data=data, base_dir=path.parent)


def validate(contract: Contract, today: date | None = None) -> list[Issue]:
    """Return all schema (E000) and semantic (S0xx) issues."""
    issues: list[Issue] = []
    validator = Draft202012Validator(SCHEMA)
    for err in validator.iter_errors(contract.data):
        pointer = "/" + "/".join(str(p) for p in err.absolute_path)
        issues.append(Issue("E000", pointer if pointer != "/" else "", err.message))
    if issues:
        return issues  # semantic checks assume a structurally valid document
    issues.extend(_semantic(contract, today or date.today()))
    return issues


# --------------------------------------------------------------------------- helpers


def macro_names(input_id: str, spec: dict[str, Any]) -> list[str]:
    """Macro names set by one input, upper-cased, in 5.7 order."""
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
    out: list[str] = []
    for iid, spec in (data.get("inputs") or {}).items():
        out.extend(macro_names(iid, spec))
    return out


def superq_macros(data: dict[str, Any]) -> set[str]:
    """Macros that need %superq: only raw text/choice (spec 6.3)."""
    out: set[str] = set()
    for iid, spec in (data.get("inputs") or {}).items():
        if spec["type"] in ("text", "choice") and spec.get("render", "raw") == "raw":
            out.update(macro_names(iid, spec))
    return out


def choice_values(spec: dict[str, Any]) -> list[str] | None:
    if "choices" not in spec:
        return None
    return [c if isinstance(c, str) else c["value"] for c in spec["choices"]]


def resolve_date(value: str, today: date) -> date:
    return today if value == "today" else date.fromisoformat(value)


def _is_int(x: Any) -> bool:
    return isinstance(x, int) and not isinstance(x, bool) or (isinstance(x, float) and x.is_integer())


def _check_regex(pattern: str) -> str | None:
    for rx, what in _FORBIDDEN_REGEX:
        if rx.search(pattern):
            return what
    try:
        re.compile(pattern)
    except re.error as exc:
        return f"does not compile: {exc}"
    return None


# --------------------------------------------------------------------------- semantic layer (3.2)


def _semantic(contract: Contract, today: date) -> list[Issue]:
    d = contract.data
    inputs: dict[str, Any] = d.get("inputs") or {}
    outputs: dict[str, Any] = d["outputs"]
    issues: list[Issue] = []

    # S001 / S002
    seen: dict[str, str] = {}
    for iid, spec in inputs.items():
        for name in macro_names(iid, spec):
            if name in seen:
                issues.append(Issue("S001", f"/inputs/{iid}", f"macro {name} also set by {seen[name]}"))
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
            bad_bare = vals is not None and any(not (SAS_NAME.match(v) or NUMERIC_LITERAL.match(v)) for v in vals)
            if spec.get("render") == "bare" and bad_bare:
                issues.append(Issue("S007", f"{p}/choices", "bare render needs SAS names or numbers"))
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
        if kind == "dataset" and "sample" in spec and not (contract.base_dir / spec["sample"]).is_file():
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
            _, errs = render_values(d, {iid: default}, today, only=[iid])
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
                issues.append(Issue("S010", f"/inputs/{iid}/target", f"target also used by {targets[t]}"))
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


# --------------------------------------------------------------------------- rendering (sections 4-5)


def render_number(x: float) -> str:
    if x == 0:
        return "0"
    if float(x).is_integer() and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.15g}".replace("e", "E")


def render_text(v: str, mode: str) -> str:
    if mode == "quoted":
        return "'" + v.replace("'", "''") + "'"
    if mode == "dquoted":
        return '"' + v.replace('"', '""') + '"'
    return v


def render_date(dt: date, mode: str) -> str:
    if mode == "date9":
        return f"{dt.day:02d}{MONTHS[dt.month - 1]}{dt.year:04d}"
    if mode == "iso":
        return dt.isoformat()
    if mode == "sasdate":
        return str((dt - SAS_EPOCH).days)
    return f"'{dt.day:02d}{MONTHS[dt.month - 1]}{dt.year:04d}'d"


_WS = "\t\n\x0b\x0c\r \x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"


def _ws_strip(v: str) -> str:
    return v.strip(_WS)


def render_values(
    data: dict[str, Any],
    values: dict[str, Any],
    today: date,
    only: list[str] | None = None,
    choices_override: dict[str, list[str]] | None = None,
    uploads: dict[str, bool] | None = None,
) -> tuple[dict[str, str], list[Issue]]:
    """Validate and render values. Returns (macros in 5.7 order, issues)."""
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
        if isinstance(raw, str) and kind in ("text", "choice"):
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


def _render_one(
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
        if "pattern" in spec and not re.fullmatch(spec["pattern"], raw):
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
        parts = [v if mode == "bare" else render_text(v, mode) for v in ordered]
        sep = ", " if spec.get("separator", "space") == "comma" else " "
        out = [sep.join(parts)]
        if "count_macro" in spec:
            out.append(str(len(parts)))
        return None, out
    if kind in ("date", "daterange"):
        items = [raw] if kind == "date" else raw
        if kind == "daterange" and (not isinstance(raw, list) or len(raw) != 2):
            return Issue("V002", iid), []
        dates: list[date] = []
        for it in items:
            if not isinstance(it, str):
                return Issue("V002", iid), []
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", it):
                    raise ValueError
                dt = resolve_date(it, today)
            except ValueError:
                return Issue("V009", iid), []
            if ("min" in spec and dt < resolve_date(spec["min"], today)) or ("max" in spec and dt > resolve_date(spec["max"], today)):
                return Issue("V009", iid), []
            dates.append(dt)
        if kind == "daterange" and dates[0] > dates[1]:
            return Issue("V010", iid), []
        mode = spec.get("render", "literal")
        return None, [render_date(x, mode) for x in dates]
    raise AssertionError(kind)


# --------------------------------------------------------------------------- wrapper (section 6)


def reset_code(data: dict[str, Any]) -> str:
    lines = ["/* SAShiny 1 reset */", "proc datasets library=work kill nolist nowarn;", "quit;"]
    names = all_macro_names(data)
    if names:
        lines.append(f"%symdel {' '.join(names)} / nowarn;")
    return "\n".join(lines) + "\n"


def wrapper_code(data: dict[str, Any], macros: dict[str, str], program_bytes: bytes, run_id: str = "fixture") -> str:
    text = program_bytes.decode("utf-8")
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    out = ["/* SAShiny 1 wrapper: generated, do not edit */", f"%put NOTE: SASHINY-BEGIN run={run_id};", "%let syscc = 0;"]
    if macros:
        out.append("data _null_;")
        for name, value in macros.items():
            out.append(f"  call symputx('{name}', '{value.replace(chr(39), chr(39) * 2)}', 'G');")
        out.append("run;")
        needs_superq = superq_macros(data)
        for name in macros:
            if name in needs_superq:
                out.append(f"%let {name} = %superq({name});")
    ods = [(oid, spec["format"]) for oid, spec in data["outputs"].items() if spec["type"] == "download" and spec["format"] in ODS_FORMATS]
    for oid, fmt in ods:
        out.append(f'ods {fmt}(id={oid}) file="%sysfunc(pathname(work))/sashiny_{oid}.{fmt}";')
    out.append("%put NOTE: SASHINY-BEGIN-PROGRAM;")
    body = "\n".join(out) + "\n" + text
    tail: list[str] = []
    run = data.get("run") or {}
    if run.get("entry") == "macro":
        args = ", ".join(f"{n}=&{n}" for n in macros)
        tail.append(f"%{run['macro']}({args});")
    tail.append("%put NOTE: SASHINY-END-PROGRAM;")
    tail.extend(f"ods {fmt}(id={oid}) close;" for oid, fmt in ods)
    tail.append(f"%put NOTE: SASHINY-END run={run_id} syscc=&syscc;")
    return body + "\n".join(tail) + "\n"


# --------------------------------------------------------------------------- collection (section 8)

_IMG = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']data:(image/[A-Za-z0-9.+-]+);base64,([^"']+)["']""", re.IGNORECASE)
_SVG = re.compile(r"<svg\b.*?</svg>", re.IGNORECASE | re.DOTALL)


def split_log(log: str) -> list[str]:
    """Split a log into lines (8.2 log): CRLF/CR/LF, no empty final line, trailing whitespace dropped."""
    lines = re.split(r"\r\n|\r|\n", log)
    if lines and lines[-1] == "" and re.search(r"(\r\n|\r|\n)$", log):
        lines.pop()
    return [ln.rstrip() for ln in lines] if log else []


def log_level(line: str) -> str:
    for prefix, level in (("ERROR", "error"), ("WARNING", "warning"), ("NOTE", "note")):
        if line.startswith(prefix):
            return level
    return "text"


def scope_log(log: str, scope: str = "program") -> list[dict[str, str]]:
    lines = split_log(log)
    if scope == "program":
        try:
            begin = lines.index("NOTE: SASHINY-BEGIN-PROGRAM")
        except ValueError:
            return []
        rest = lines[begin + 1 :]
        end = rest.index("NOTE: SASHINY-END-PROGRAM") if "NOTE: SASHINY-END-PROGRAM" in rest else len(rest)
        lines = rest[:end]
    return [{"level": log_level(ln), "text": ln} for ln in lines]


def extract_plots(html: str, select: int | None = None) -> list[dict[str, str]]:
    import base64

    found: list[tuple[int, dict[str, str]]] = []
    for m in _IMG.finditer(html):
        found.append((m.start(), {"mime": m.group(1).lower(), "data": m.group(2)}))
    for m in _SVG.finditer(html):
        found.append((m.start(), {"mime": "image/svg+xml", "data": base64.b64encode(m.group(0).encode("utf-8")).decode("ascii")}))
    plots = [p for _, p in sorted(found, key=lambda t: t[0])]
    if select is None:
        return plots
    if select > len(plots):
        raise ValueError(f"select={select} but only {len(plots)} graph(s) were produced")
    return [plots[select - 1]]


def recording_key_text(contract_sha256: str, macros: list[tuple[str, str]], uploads: list[tuple[str, str]]) -> str:
    lines = ["sashiny-recording-key 1", f"contract {contract_sha256}"]
    lines += [f"macro {n}={v}" for n, v in macros]
    lines += [f"upload {i} {h}" for i, h in uploads]
    return "\n".join(lines) + "\n"


def recording_key(contract_sha256: str, macros: list[tuple[str, str]], uploads: list[tuple[str, str]]) -> str:
    import hashlib

    return hashlib.sha256(recording_key_text(contract_sha256, macros, uploads).encode("utf-8")).hexdigest()
