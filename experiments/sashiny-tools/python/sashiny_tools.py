"""Expose a SAShiny contract as a chatlas tool (experiment, #130 J7; not shipped).

A contract already declares typed inputs with limits, choices and defaults. This
module maps them to a JSON Schema so a chat model can call a validated SAS
program instead of writing SAS code. The model only picks input values; SAShiny
validates them (V001-V014) and SAS does the computation.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

import sashiny
from sashiny.contract import resolve_date

__all__ = ["as_tool", "call", "summarise", "tool_name", "tool_schema"]

PREVIEW_ROWS = 20


def tool_name(contract: sashiny.Contract) -> str:
    """Return the tool name: the contract file stem (``x.sashiny.yml`` -> ``x``)."""
    stem = contract.path.name if contract.path is not None else contract.data["program"]
    stem = re.sub(r"(\.sashiny)?\.ya?ml$|\.sas$", "", stem, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9_-]", "_", stem)[:64] or "sas_program"


def _description(contract: sashiny.Contract) -> str:
    data = contract.data
    parts = [data.get("title", ""), (data.get("description") or "").strip()]
    parts.append(
        "Runs a validated SAS program; returns status, the first ERROR and table previews."
    )
    return " ".join(p for p in parts if p)


def _values(spec: dict[str, Any]) -> list[str]:
    return [c["value"] if isinstance(c, dict) else str(c) for c in spec.get("choices", [])]


def _property(spec: dict[str, Any], today: date) -> dict[str, Any]:  # noqa: PLR0912 - one branch per input type
    kind = spec["type"]
    label = spec.get("label", "")
    if kind == "numeric":
        prop: dict[str, Any] = {"type": "integer" if spec.get("integer") else "number"}
        if "min" in spec:
            prop["minimum"] = spec["min"]
        if "max" in spec:
            prop["maximum"] = spec["max"]
        return {**prop, "description": label}
    if kind == "text":
        prop = {"type": "string", "description": label}
        if "max_length" in spec:
            prop["maxLength"] = spec["max_length"]
        if "pattern" in spec:
            prop["pattern"] = spec["pattern"]
        return prop
    if kind == "choice":
        prop = {"type": "string", "description": label}
        if "choices" in spec:
            prop["enum"] = _values(spec)
        return prop
    if kind == "multichoice":
        items: dict[str, Any] = {"type": "string"}
        if "choices" in spec:
            items["enum"] = _values(spec)
        prop = {"type": "array", "items": items, "uniqueItems": True, "description": label}
        if "min_selected" in spec:
            prop["minItems"] = spec["min_selected"]
        if "max_selected" in spec:
            prop["maxItems"] = spec["max_selected"]
        return prop
    if kind == "date":
        return {"type": "string", "format": "date", "description": _date_hint(label, spec, today)}
    # daterange
    return {
        "type": "array",
        "items": {"type": "string", "format": "date"},
        "minItems": 2,
        "maxItems": 2,
        "description": _date_hint(f"{label} [start, end]", spec, today),
    }


def _date_hint(label: str, spec: dict[str, Any], today: date) -> str:
    bounds = [
        f"{word} {resolve_date(spec[key], today).isoformat()}"
        for key, word in (("min", "from"), ("max", "to"))
        if key in spec
    ]
    return " ".join([label, "(ISO date YYYY-MM-DD", *bounds]).strip() + ")"


def tool_schema(contract: sashiny.Contract, today: date | None = None) -> dict[str, Any]:
    """Return the JSON Schema of the tool's arguments (dataset inputs are not exposed)."""
    today = today or date.today()
    props: dict[str, Any] = {}
    required: list[str] = []
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if spec["type"] == "dataset":
            continue
        props[iid] = _property(spec, today)
        if not spec.get("optional", False) and "default" not in spec:
            required.append(iid)
    return {"type": "object", "properties": props, "required": required}


def _with_defaults(contract: sashiny.Contract, args: dict[str, Any], today: date) -> dict[str, Any]:
    values = dict(args)
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if iid in values or "default" not in spec or spec["type"] == "dataset":
            continue
        default = spec["default"]
        if spec["type"] == "date":
            default = resolve_date(default, today).isoformat()
        elif spec["type"] == "daterange":
            default = [resolve_date(d, today).isoformat() for d in default]
        values[iid] = default
    return values


def _first_error(log: str) -> str | None:
    for line in log.splitlines():
        if line.startswith("ERROR"):
            return line.strip()
    return None


def summarise(contract: sashiny.Contract, result: sashiny.Result) -> dict[str, Any]:
    """Return the compact JSON summary sent back to the model (no raw HTML)."""
    tables: dict[str, Any] = {}
    for oid, spec in contract.data.get("outputs", {}).items():
        value = result.outputs.get(oid)
        if spec["type"] != "table" or not isinstance(value, dict) or "rows" not in value:
            continue
        rows = value["rows"]
        tables[oid] = {
            "columns": [c["name"] if isinstance(c, dict) else c for c in value.get("columns", [])],
            "rows": rows[:PREVIEW_ROWS],
            "total_rows": value.get("total_rows", len(rows)),
        }
    return {
        "run_id": result.run_id,
        "status": result.status,
        "error": _first_error(result.log or ""),
        "issues": result.metadata.get("issues", []),
        "tables": tables,
    }


def call(
    contract: sashiny.Contract,
    engine: sashiny.Engine,
    args: dict[str, Any],
    today: date | None = None,
) -> str:
    """Run the contract with model-supplied ``args``; return the JSON summary.

    Invalid arguments are returned to the model as V-code issues, never raised.
    """
    today = today or date.today()
    try:
        result = sashiny.run(contract, _with_defaults(contract, args, today), engine, today=today)
    except Exception as exc:
        return json.dumps({"run_id": None, "status": "error", "error": str(exc), "issues": []})
    return json.dumps(summarise(contract, result), default=str)


def as_tool(contract: sashiny.Contract, engine: sashiny.Engine) -> Any:
    """Return a :class:`chatlas.Tool` that runs ``contract`` on ``engine``."""
    from chatlas import Tool  # noqa: PLC0415 - optional, experiment only

    def run_contract(**kwargs: Any) -> str:
        return call(contract, engine, kwargs)

    return Tool(
        func=run_contract,
        name=tool_name(contract),
        description=_description(contract),
        parameters=tool_schema(contract),
    )
