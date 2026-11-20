"""Tests for the runner layer."""

from __future__ import annotations

from datetime import date

import pytest

import sashiny
from _repo import repo_root
from engines_helper import MockEngine

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def test_run_with_contract_object() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    result = sashiny.run(contract, MockEngine(), today=TODAY)
    assert result.status == "success"


def test_run_with_contract_path() -> None:
    path = FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml"
    result = sashiny.run(path, MockEngine(), today=TODAY)
    assert result.status == "success"


def test_run_reports_invalid_values() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = sashiny.run(contract, MockEngine(), {"min_msrp": "bad"}, today=TODAY)
    assert result.status == "error"


def test_old_argument_order_still_works_with_a_warning() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    with pytest.warns(DeprecationWarning, match="pass the engine second"):
        result = sashiny.run(contract, {}, MockEngine(), today=TODAY)
    assert result.status == "success"


def test_close_closes_an_engine_or_pool() -> None:
    pool = sashiny.Pool(MockEngine(), max_size=1)
    sashiny.close(pool)
    sashiny.close(pool)
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    assert "pool closed" in sashiny.run(contract, pool).metadata["engine_error"]
