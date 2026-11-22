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


def _contract(name: str) -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / name / "contract.sashiny.yml")


def test_run_without_values_uses_the_contract_defaults() -> None:
    # Issue #162: inputs not supplied take their `default` (spec §6.12).
    for values in (None, {}):
        result = sashiny.run(_contract("numeric"), MockEngine(), values, today=TODAY)
        assert result.status == "success"
        assert result.metadata["macros"]["MIN_MSRP"] == "20000"
        assert result.metadata["macros"]["RATIO_VALUE"] == "0.5"
        assert result.metadata["macros"]["BIG"] == ""


def test_run_resolves_today_defaults_against_today() -> None:
    result = sashiny.run(_contract("dates"), MockEngine(), today=TODAY)
    assert result.status == "success"
    macros = result.metadata["macros"]
    assert macros["CUTOFF"] == "'11NOV2026'd"
    assert macros["PERIOD_START"] == "'01JAN2026'd"
    assert macros["PERIOD_END"] == "'30JUN2026'd"


def test_run_supplied_values_replace_defaults_and_none_is_absent() -> None:
    result = sashiny.run(_contract("numeric"), MockEngine(), {"min_msrp": 5000}, today=TODAY)
    assert result.metadata["macros"]["MIN_MSRP"] == "5000"
    assert result.metadata["macros"]["RATIO_VALUE"] == "0.5"
    absent = sashiny.run(_contract("numeric"), MockEngine(), {"ratio": None}, today=TODAY)
    assert absent.status == "error"
    assert [i["code"] for i in absent.metadata["issues"]] == ["V001"]
    assert absent.metadata["issues"][0]["input"] == "ratio"


def test_run_defaults_fill_multichoice_inputs() -> None:
    # `types` has no default, so it is absent unless supplied (spec §6.12).
    missing = sashiny.run(_contract("multichoice"), MockEngine(), today=TODAY)
    assert [(i["code"], i["input"]) for i in missing.metadata["issues"]] == [("V001", "types")]
    result = sashiny.run(_contract("multichoice"), MockEngine(), {"types": []}, today=TODAY)
    assert result.status == "success"
    assert result.metadata["macros"]["ORIGINS"] == "'Asia' 'Europe' 'USA'"
    assert result.metadata["macros"]["N_ORIGINS"] == "3"
