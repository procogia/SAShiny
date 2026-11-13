"""Tests for the runner layer."""

from __future__ import annotations

from datetime import date

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def test_run_with_contract_object() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    result = sashiny.run(contract, {}, sashiny.MockEngine(), today=TODAY)
    assert result.status == "success"


def test_run_with_contract_path() -> None:
    path = FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml"
    result = sashiny.run(path, {}, sashiny.MockEngine(), today=TODAY)
    assert result.status == "success"


def test_run_reports_invalid_values() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = sashiny.run(contract, {"min_msrp": "bad"}, sashiny.MockEngine(), today=TODAY)
    assert result.status == "error"
