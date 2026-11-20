"""Tests for the contract-as-tool experiment (mock engine only)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

import sashiny
from sashiny.engines._mock import MockEngine
from sashiny.result import Result

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sashiny_tools as st

ROOT = Path(__file__).resolve().parents[4]
FIX = ROOT / "spec" / "fixtures" / "contracts" / "valid"
TODAY = date(2026, 11, 11)


def _load(name: str) -> sashiny.Contract:
    return sashiny.load(FIX / name / "contract.sashiny.yml")


def test_name_and_description() -> None:
    cars = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    assert st.tool_name(cars) == "cars_explorer"
    tool = st.as_tool(cars, MockEngine())
    assert tool.name == "cars_explorer"
    assert "Car price explorer" in tool.schema["function"]["description"]


def test_numeric_mapping() -> None:
    props = st.tool_schema(_load("numeric"), TODAY)
    assert props["properties"]["min_msrp"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 200000,
        "description": "Minimum MSRP",
    }
    assert props["properties"]["ratio"]["type"] == "number"
    assert props["required"] == []


def test_choice_and_multichoice_mapping() -> None:
    m = st.tool_schema(_load("multichoice"), TODAY)["properties"]
    assert m["origins"]["items"]["enum"] == ["Asia", "Europe", "USA"]
    assert m["types"]["maxItems"] == 2
    assert m["types"]["minItems"] == 0
    c = st.tool_schema(_load("choice"), TODAY)["properties"]
    assert all(p["type"] == "string" for p in c.values())
    assert any("enum" in p for p in c.values())


def test_date_mapping() -> None:
    d = st.tool_schema(_load("dates"), TODAY)["properties"]
    assert d["cutoff"]["format"] == "date"
    assert "to 2026-11-11" in d["cutoff"]["description"]
    assert d["period"]["minItems"] == d["period"]["maxItems"] == 2


def test_text_mapping() -> None:
    t = st.tool_schema(_load("text"), TODAY)["properties"]
    assert all(p["type"] == "string" for p in t.values())


def test_dataset_inputs_are_not_exposed() -> None:
    schema = st.tool_schema(_load("dataset"), TODAY)
    assert schema["properties"] == {}


def test_valid_call_returns_summary() -> None:
    out = json.loads(st.call(_load("numeric"), MockEngine(), {"min_msrp": 30000}, TODAY))
    assert out["status"] == "success"
    assert out["run_id"]
    assert out["issues"] == []


def test_invalid_arguments_become_v_codes() -> None:
    out = json.loads(
        st.call(_load("numeric"), MockEngine(), {"min_msrp": 999999, "bogus": 1}, TODAY)
    )
    assert out["status"] == "error"
    assert {i["code"] for i in out["issues"]} == {"V003", "V011"}
    wrong_type = json.loads(st.call(_load("numeric"), MockEngine(), {"min_msrp": "lots"}, TODAY))
    assert wrong_type["issues"][0]["code"] == "V002"


def test_summary_previews_tables_and_first_error() -> None:
    contract = _load("outputs")
    tables = [o for o, s in contract.data["outputs"].items() if s["type"] == "table"]
    if not tables:
        pytest.skip("fixture has no table output")
    result = Result.new("r1", "warning")
    result.log = "NOTE: ok\nERROR: Variable X not found.\nERROR: second\n"
    result.outputs[tables[0]] = {
        "columns": [{"name": "a"}],
        "rows": [[i] for i in range(30)],
        "total_rows": 30,
    }
    result.outputs["report"] = "<html>never sent</html>"
    out = st.summarise(contract, result)
    assert out["error"] == "ERROR: Variable X not found."
    assert len(out["tables"][tables[0]]["rows"]) == 20
    assert out["tables"][tables[0]]["total_rows"] == 30
    assert "<html>" not in json.dumps(out)
