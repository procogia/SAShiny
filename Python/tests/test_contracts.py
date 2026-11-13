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
