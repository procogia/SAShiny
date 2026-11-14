"""Tests for the bounded session pool (issue #7)."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
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


class _RaisingEngine(sashiny.Engine):
    closed = 0

    def run(self, contract, values, *, today=None, uploads=None, run_id=None):  # type: ignore[no-untyped-def]
        raise RuntimeError("synthetic transport error")

    def close(self) -> None:
        _RaisingEngine.closed += 1


def test_pool_discards_session_when_engine_raises() -> None:
    _RaisingEngine.closed = 0
    pool = sashiny.Pool(_RaisingEngine, max_size=1)
    contract = _minimal_contract()
    result = pool.run(contract, {}, today=TODAY)
    assert result.status == "error"
    assert "synthetic transport error" in result.metadata["engine_error"]
    assert len(pool._sessions) == 0
    assert _RaisingEngine.closed == 1
    pool.close()


def test_pool_warms_min_size_sessions() -> None:
    made: list[sashiny.Engine] = []

    def factory() -> sashiny.Engine:
        engine = sashiny.MockEngine()
        made.append(engine)
        return engine

    pool = sashiny.Pool(factory, min_size=2, max_size=3)
    assert len(made) == 2
    assert len(pool._sessions) == 2
    pool.close()


def test_pool_rejects_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="min_size"):
        sashiny.Pool(sashiny.MockEngine(), min_size=3, max_size=2)
    with pytest.raises(ValueError, match="non-negative"):
        sashiny.Pool(sashiny.MockEngine(), min_size=-1)


class _SlowEngine(sashiny.Engine):
    def __init__(self) -> None:
        self._started = threading.Event()

    def run(self, contract, values, *, today=None, uploads=None, run_id=None):  # type: ignore[no-untyped-def]
        self._started.set()
        time.sleep(0.3)
        return sashiny.Result.new(run_id or "r", "success")

    def close(self) -> None:
        pass


def test_pool_waits_for_a_free_session() -> None:
    pool = sashiny.Pool(_SlowEngine, max_size=1, acquire_timeout=5.0)
    contract = _minimal_contract()
    results: list[sashiny.Result] = []

    def run() -> None:
        results.append(pool.run(contract, {}, today=TODAY))

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(r.status == "success" for r in results)
    pool.close()


def test_pool_returns_error_result_when_exhausted() -> None:
    pool = sashiny.Pool(_SlowEngine, max_size=1, acquire_timeout=0.1)
    contract = _minimal_contract()
    results: list[sashiny.Result] = []

    def run() -> None:
        results.append(pool.run(contract, {}, today=TODAY))

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    statuses = sorted(r.status for r in results)
    assert statuses == ["error", "error", "success"]
    exhausted = [r for r in results if r.status == "error"]
    assert all("pool exhausted" in r.metadata["engine_error"] for r in exhausted)
    pool.close()


def test_pool_close_stops_creating_sessions() -> None:
    made: list[sashiny.Engine] = []

    def factory() -> sashiny.Engine:
        engine = sashiny.MockEngine()
        made.append(engine)
        return engine

    pool = sashiny.Pool(factory, min_size=2, max_size=4)
    assert len(made) == 2
    pool.close()
    # After close, no new sessions may be created (issue #80).
    assert len(made) == 2
    assert pool._sessions == []


def test_pool_run_after_close_returns_error() -> None:
    pool = sashiny.Pool(sashiny.MockEngine(), max_size=2)
    contract = _minimal_contract()
    pool.close()
    result = pool.run(contract, {}, today=TODAY)
    assert result.status == "error"
    assert "pool closed" in result.metadata["engine_error"]


def test_pool_close_during_inflight_run_does_not_resurrect() -> None:
    pool = sashiny.Pool(_SlowEngine, max_size=1, acquire_timeout=5.0)
    contract = _minimal_contract()
    result_holder: list[sashiny.Result] = []

    def run() -> None:
        result_holder.append(pool.run(contract, {}, today=TODAY))

    t = threading.Thread(target=run)
    t.start()
    # Wait until the slow engine has actually started, then close the pool.
    pool._sessions[0].engine._started.wait(timeout=5.0)
    pool.close()
    t.join()
    # The in-flight run completes, but close() must not have re-created any
    # session via _top_up/_release (issue #80).
    assert result_holder[0].status == "success"
    assert pool._sessions == []


class _FactoryFailingEngine(sashiny.Engine):
    def run(self, contract, values, *, today=None, uploads=None, run_id=None):  # type: ignore[no-untyped-def]
        return sashiny.Result.new(run_id or "r", "success")

    def close(self) -> None:
        pass


def test_pool_factory_failure_returns_error_result() -> None:
    # Issue #75: a lazy engine-factory exception during acquisition must become
    # an error Result, not escape from Pool.run.
    def factory() -> sashiny.Engine:
        raise RuntimeError("connection refused")

    pool = sashiny.Pool(factory, min_size=0, max_size=1)
    contract = _minimal_contract()
    result = pool.run(contract, {}, today=TODAY)
    assert result.status == "error"
    assert "connection refused" in result.metadata["engine_error"]
