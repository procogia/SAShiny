"""Conformance tests for the contract loader and validator (issues #2).

Reads ``spec/fixtures/contracts`` and asserts the same behaviour as the
reference oracle: valid contracts produce no issues; invalid contracts produce
the exact ``{code, path}`` set (schema ``E000``: at least the listed paths).
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def _valid_contracts() -> list[Path]:
    return sorted((FIX / "contracts" / "valid").glob("*/contract.sashiny.yml"))


def _invalid_contracts() -> list[Path]:
    return sorted((FIX / "contracts" / "invalid").glob("*/contract.sashiny.yml"))


@pytest.mark.parametrize("yml", _valid_contracts(), ids=lambda p: p.parent.name)
def test_valid_contracts(yml: Path) -> None:
    contract = sashiny.load(yml)
    issues = sashiny.validate(contract, TODAY)
    assert not issues, "; ".join(f"{i.code} {i.path} {i.message}" for i in issues)


@pytest.mark.parametrize("yml", _invalid_contracts(), ids=lambda p: p.parent.name)
def test_invalid_contracts(yml: Path) -> None:
    expected = json.loads((yml.parent / "expected.json").read_text(encoding="utf-8"))
    want = {(e["code"], e["path"]) for e in expected["errors"]}
    contract = sashiny.load(yml)
    got_issues = sashiny.validate(contract, TODAY)
    got = {i.key() for i in got_issues}
    if all(c == "E000" for c, _ in want):
        # Schema errors: the expected path must be reported; exact messages vary.
        paths_found = all(
            any(gp.startswith(p) or p.startswith(gp) for _, gp in got) for _, p in want
        )
        assert bool(got)
        assert all(c == "E000" for c, _ in got)
        assert paths_found, f"want {sorted(want)} got {sorted(got)}"
    else:
        assert got == want, f"want {sorted(want)} got {sorted(got)}"


def _data(**overrides: object) -> dict:
    data = {
        "sashiny": 1,
        "program": "program.sas",
        "title": "t",
        "outputs": {"log": {"type": "log"}},
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("kind", ["date", "daterange"])
@pytest.mark.parametrize("bound", ["min", "max"])
def test_one_sided_date_bound_is_valid(kind: str, bound: str) -> None:
    # A date/daterange with only min or only max is valid (issue #70).
    data = _data(inputs={"x": {"type": kind, "label": "X", bound: "2026-01-01"}})
    contract = sashiny.Contract(data, FIX / "contracts" / "valid" / "minimal")
    assert sashiny.validate(contract, TODAY) == []


def test_one_sided_date_bound_invalid_value_is_s003() -> None:
    # A present-but-invalid bound is still S003.
    data = _data(inputs={"x": {"type": "date", "label": "X", "min": "2026-02-30"}})
    contract = sashiny.Contract(data, FIX / "contracts" / "valid" / "minimal")
    issues = sashiny.validate(contract, TODAY)
    assert [i.key() for i in issues] == [("S003", "/inputs/x")]


@pytest.mark.parametrize("pattern", ["[+?]", "[(?=]", "[*+]", "[a-z+?]"])
def test_literal_character_classes_are_portable(pattern: str) -> None:
    # Literal quantifier/look-around tokens inside a class are not forbidden (#82).
    data = _data(inputs={"x": {"type": "text", "label": "X", "pattern": pattern}})
    contract = sashiny.Contract(data, FIX / "contracts" / "valid" / "minimal")
    assert sashiny.validate(contract, TODAY) == []


def test_forbidden_construct_outside_class_is_s014() -> None:
    data = _data(inputs={"x": {"type": "text", "label": "X", "pattern": "a+?"}})
    contract = sashiny.Contract(data, FIX / "contracts" / "valid" / "minimal")
    issues = sashiny.validate(contract, TODAY)
    assert [i.key() for i in issues] == [("S014", "/inputs/x/pattern")]
