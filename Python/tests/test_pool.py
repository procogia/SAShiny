"""Tests for the bounded session pool (issue #7)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import sashiny

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def test_pool_runs_contract() -> None:
    pool = sashiny.Pool(sashiny.MockEngine(), max_size=2)
    contract = _minimal_contract()
    result = pool.run(contract, {}, today=TODAY)
    assert result.status == "success"
    pool.close()


def test_pool_reuses_session() -> None:
    pool = sashiny.Pool(sashiny.MockEngine(), max_size=2)
    contract = _minimal_contract()
    pool.run(contract, {}, today=TODAY)
    pool.run(contract, {}, today=TODAY)
    # Both runs should have reused the same single session (max_size=2, but
    # only one session is ever needed sequentially).
    assert len(pool._sessions) == 1
    assert pool._sessions[0].runs == 2
    pool.close()


def test_pool_discards_on_error() -> None:
    pool = sashiny.Pool(sashiny.MockEngine(), max_size=2)
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = pool.run(contract, {"min_msrp": "bad"}, today=TODAY)
    assert result.status == "error"
    # The errored session should have been discarded.
    assert len(pool._sessions) == 0
    pool.close()
