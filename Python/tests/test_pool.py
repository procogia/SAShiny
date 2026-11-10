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


def test_pool_keeps_session_on_validation_error() -> None:
    pool = sashiny.Pool(sashiny.MockEngine(), max_size=2)
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = pool.run(contract, {"min_msrp": "bad"}, today=TODAY)
    assert result.status == "error"
    # Validation errors never reach SAS, so the session stays usable.
    assert len(pool._sessions) == 1
    pool.close()


class _FailingEngine(sashiny.Engine):
    closed = 0

    def run(self, contract, values, *, today=None, uploads=None, run_id=None):  # type: ignore[no-untyped-def]
        return sashiny.Result.new(run_id or "r", "error")

    def close(self) -> None:
        _FailingEngine.closed += 1


def test_pool_discards_and_closes_factory_session_on_run_error() -> None:
    _FailingEngine.closed = 0
    pool = sashiny.Pool(_FailingEngine, max_size=2)
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    assert pool.run(contract, {}, today=TODAY).status == "error"
    assert len(pool._sessions) == 0
    assert _FailingEngine.closed == 1


def test_pool_factory_gives_each_session_its_own_engine() -> None:
    pool = sashiny.Pool(sashiny.MockEngine, max_size=2)
    a = pool._acquire()
    b = pool._acquire()
    assert a.engine is not b.engine
    pool._release(a, discard=False)
    pool._release(b, discard=False)
    pool.close()
    assert pool._sessions == []
