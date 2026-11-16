"""Smoke tests for the demo app (live SAS only; no SAS in CI)."""

from __future__ import annotations

import importlib.util
import sys
import time
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


def test_demo_connection_choices_and_prerequisite(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SASHINY_PROFILE", raising=False)
    demo = _demo()
    assert demo.PROFILES == {
        "oda": "SAS ODA (OnDemand for Academics)",
        "viya": "SAS Viya",
        "sas94": "SAS 9.4",
    }
    assert demo.PROFILE == "oda"
    html = str(demo.app_ui)
    assert "responsible for obtaining access to a compatible SAS compiler" in html
    assert "SAShiny does not provide SAS" in html


def test_demo_without_licence_ack_reports_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SASHINY_LICENSE_ACK", raising=False)
    monkeypatch.setenv("SASHINY_PROFILE", "viya")
    monkeypatch.setenv("SASHINY_VIYA_URL", "https://viya.example.com")
    demo = _demo()
    with test_server(demo.app) as session:
        session.set_inputs(**{"general-run": 1})
        for _ in range(50):
            session.flush()
            status = session.get_output("general-status").value
            if status != "running...":
                break
            time.sleep(0.05)
        assert "SAS licence not acknowledged" in status


def test_demo_rejects_unknown_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SASHINY_PROFILE", "offline")
    with pytest.raises(ValueError, match="SASHINY_PROFILE"):
        _demo()
