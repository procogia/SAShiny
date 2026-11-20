"""choices_from caching (spec §6.4, #130 J3). No SAS: a counting mock engine."""

from __future__ import annotations

import dataclasses
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from shiny import App, ui

import sashiny
from engines_helper import MockEngine
from sashiny import choices_cache
from sashiny.modules import program_server, program_ui

TODAY = date(2026, 11, 11)


class CountingEngine(MockEngine):
    """The mock engine, counting choices queries."""

    def __init__(self, fail: bool = False) -> None:
        super().__init__(choices={"make": ["Acura", "BMW"]})
        self.queries = 0
        self.fail = fail

    def choices(self, contract: sashiny.Contract) -> dict[str, list[dict[str, str]]]:
        self.queries += 1
        if self.fail:
            raise RuntimeError("library SASHELP is not assigned")
        return super().choices(contract)


def _contract(tmp_path: Path, ttl: int | None = None) -> sashiny.Contract:
    (tmp_path / "program.sas").write_text("data _null_; run;\n", encoding="utf-8")
    text = (
        "sashiny: 1\nprogram: program.sas\ntitle: Choices\ninputs:\n  make:\n    type: choice\n"
        "    label: Make\n    choices_from: {dataset: sashelp.cars, value_column: make}\n"
        "outputs:\n  log:\n    type: log\n"
    )
    if ttl is not None:
        text += f"run:\n  choices_ttl_seconds: {ttl}\n"
    path = tmp_path / "c.sashiny.yml"
    path.write_text(text, encoding="utf-8")
    return sashiny.load(path)


def test_load_queries_once_then_uses_the_cache(tmp_path: Path) -> None:
    engine = CountingEngine()
    contract = _contract(tmp_path)
    for _ in range(5):
        assert [c["value"] for c in choices_cache.load(engine, contract)["make"]] == [
            "Acura",
            "BMW",
        ]
    assert engine.queries == 1


def test_ttl_expiry_and_zero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = CountingEngine()
    contract = _contract(tmp_path, ttl=60)
    choices_cache.load(engine, contract)
    now = time.monotonic()
    monkeypatch.setattr(choices_cache.time, "monotonic", lambda: now + 61)
    choices_cache.load(engine, contract)
    assert engine.queries == 2
    zero_engine = CountingEngine()
    (tmp_path / "zero").mkdir()
    zero = _contract(tmp_path / "zero", ttl=0)
    choices_cache.load(zero_engine, zero)
    choices_cache.load(zero_engine, zero)
    assert zero_engine.queries == 2


def test_clear_and_failures_are_not_cached(tmp_path: Path) -> None:
    engine = CountingEngine()
    contract = _contract(tmp_path)
    choices_cache.load(engine, contract)
    choices_cache.clear(engine)
    assert choices_cache.cached(engine, contract) is None
    broken = CountingEngine(fail=True)
    with pytest.raises(RuntimeError):
        choices_cache.load(broken, contract)
    assert choices_cache.cached(broken, contract) is None


def test_run_before_choices_load_still_validates(tmp_path: Path) -> None:
    engine = CountingEngine()
    contract = _contract(tmp_path)
    bad = engine.run(contract, {"make": "Saab"}, today=TODAY)
    assert bad.status == "error"
    assert bad.metadata["issues"][0]["input"] == "make"
    assert engine.run(contract, {"make": "BMW"}, today=TODAY).status == "success"


def _module_app(contract: sashiny.Contract, engine: Any) -> App:
    def server(input: Any, output: Any, session: Any) -> None:
        program_server("m", contract, engine)

    return App(ui.page_fluid(program_ui("m", contract)), server)


def test_many_sessions_share_one_query(tmp_path: Path) -> None:
    # Each session's module reads the same app-level cache (spec 6.4).
    engine = CountingEngine()
    contract = _contract(tmp_path)
    choices_cache.load(engine, contract)
    for _ in range(4):
        hit = choices_cache.cached(engine, contract)
        assert hit is not None
    assert engine.queries == 1
    assert _module_app(contract, engine) is not None


def test_cached_choices_skip_the_query_in_a_run(tmp_path: Path) -> None:
    engine = CountingEngine()
    contract = _contract(tmp_path)
    found = choices_cache.load(engine, contract)
    run_contract = dataclasses.replace(contract, cached_choices=found)
    assert engine.run(run_contract, {"make": "BMW"}, today=TODAY).status == "success"
    assert engine.queries == 1
