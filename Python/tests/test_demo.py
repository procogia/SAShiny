"""Smoke tests for the Lisbon demo app (offline replay and live fallback)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("shiny.testserver")
from shiny.testserver import test_server

DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo" / "app.py"


def _demo():  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location("sashiny_demo", DEMO)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["sashiny_demo"] = module
    spec.loader.exec_module(module)
    return module


def test_demo_offline_runs_every_track() -> None:
    demo = _demo()
    with test_server(demo.app) as session:
        for tid in demo.TRACKS:
            session.set_inputs(**{f"{tid}-run": 1})
            status = session.get_output(f"{tid}-status").value
            assert "status:" in status, tid


def test_demo_live_without_settings_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SASHINY_VIYA_URL", raising=False)
    demo = _demo()
    with test_server(demo.app) as session:
        session.set_inputs(profile="viya")
        session.set_inputs(**{"general-run": 1})
        status = session.get_output("general-status").value
        assert "unavailable" in status
        assert "url is required" in status
