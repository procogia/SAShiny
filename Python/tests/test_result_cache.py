"""Tests for the opt-in result cache (spec §6.11)."""

from __future__ import annotations

import dataclasses
import json
import shutil
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import sashiny
from _repo import repo_root
from engines_helper import MockEngine
from sashiny import result_cache
from sashiny.result import Result

FIX = repo_root() / "spec" / "fixtures"
TODAY = date(2026, 11, 11)


class CountingEngine(MockEngine):
    """The mock engine, counting runs and optionally forcing a status."""

    def __init__(self, status: str | None = None) -> None:
        super().__init__()
        self.calls = 0
        self.status = status

    def run(self, contract: Any, values: Any, **kwargs: Any) -> Result:  # type: ignore[override]
        self.calls += 1
        result = super().run(contract, values, **kwargs)
        if self.status is not None and result.status == "success":
            result.status = self.status
        return result


@pytest.fixture(autouse=True)
def _fresh_store() -> Any:
    previous = result_cache.set_store(None)
    yield
    result_cache.set_store(previous)


def _contract(**run: Any) -> sashiny.Contract:
    contract = sashiny.load(FIX / "contracts" / "valid" / "result_cache" / "contract.sashiny.yml")
    data = dict(contract.data)
    data["run"] = {**data["run"], **run}
    return dataclasses.replace(contract, data=data)


def test_key_text_matches_the_fixture() -> None:
    k = json.loads((FIX / "collect" / "cache_key.json").read_text(encoding="utf-8"))
    text = result_cache.key_text(
        k["contract_sha256"],
        k["program_sha256"],
        [tuple(m) for m in k["macros"]],
        [tuple(u) for u in k["uploads"]],
    )
    assert text == k["key_text"]


def test_hit_and_miss_and_metadata() -> None:
    engine = CountingEngine()
    contract = _contract()
    first = sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert "cache_hit" not in first.metadata
    again = sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 1
    assert again.run_id == first.run_id
    assert again.metadata["cache_hit"] is True
    assert again.metadata["cached_at"].endswith("Z")
    other = sashiny.run(contract, {"n": 2}, engine, today=TODAY)
    assert engine.calls == 2
    assert other.run_id != first.run_id


def test_hits_are_copies() -> None:
    engine = CountingEngine()
    contract = _contract()
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    hit = sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    hit.outputs["x"] = 1
    assert "x" not in sashiny.run(contract, {"n": 1}, engine, today=TODAY).outputs


def test_off_by_default() -> None:
    engine = CountingEngine()
    contract = _contract(cache=False)
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 2
    plain = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    assert not result_cache.enabled(plain)


def test_ttl_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = CountingEngine()
    contract = _contract(cache_ttl_seconds=10)
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    now = time.time()
    monkeypatch.setattr(result_cache.time, "time", lambda: now + 11)
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 2


@pytest.mark.parametrize("status", ["error", "timeout"])
def test_failed_results_are_not_cached(status: str) -> None:
    engine = CountingEngine(status=status)
    contract = _contract()
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 2


def test_warning_results_are_cached() -> None:
    engine = CountingEngine(status="warning")
    contract = _contract()
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    hit = sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 1
    assert hit.status == "warning"


def test_invalid_values_bypass_the_cache() -> None:
    engine = CountingEngine()
    contract = _contract()
    bad = sashiny.run(contract, {"n": 99}, engine, today=TODAY)
    assert bad.status == "error"
    assert len(result_cache.get_store()) == 0  # type: ignore[arg-type]


def test_upload_changes_miss_the_cache(tmp_path: Path) -> None:
    src = FIX / "contracts" / "valid" / "dataset"
    work = tmp_path / "c"
    shutil.copytree(src, work)
    contract = sashiny.load(work / "contract.sashiny.yml")
    data = dict(contract.data)
    data["run"] = {"cache": True}
    contract = dataclasses.replace(contract, data=data)
    engine = CountingEngine()
    upload = tmp_path / "adsl.csv"
    upload.write_text("USUBJID,AGE,TRTSDT\nA,30,2024-01-01\n", encoding="utf-8")
    sashiny.run(contract, {}, engine, today=TODAY, uploads={"adsl": upload})
    sashiny.run(contract, {}, engine, today=TODAY, uploads={"adsl": upload})
    assert engine.calls == 1
    upload.write_text("USUBJID,AGE,TRTSDT\nB,40,2024-01-01\n", encoding="utf-8")
    sashiny.run(contract, {}, engine, today=TODAY, uploads={"adsl": upload})
    assert engine.calls == 2


def test_lru_eviction_and_custom_store() -> None:
    store = result_cache.LRUStore(max_entries=2)
    result_cache.set_store(store)
    engine = CountingEngine()
    contract = _contract()
    for n in (1, 2, 3):
        sashiny.run(contract, {"n": n}, engine, today=TODAY)
    assert len(store) == 2
    sashiny.run(contract, {"n": 1}, engine, today=TODAY)
    assert engine.calls == 4
    with pytest.raises(ValueError, match="max_entries"):
        result_cache.LRUStore(0)
