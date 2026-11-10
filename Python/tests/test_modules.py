"""Tests for the Shiny module UI (issue #9)."""

from __future__ import annotations

from pathlib import Path

import sashiny
from sashiny import modules

ROOT = Path(__file__).resolve().parents[2]


def test_program_ui_has_one_card_per_output() -> None:
    contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    html = str(modules.program_ui("cars", contract))
    for oid, spec in contract.data["outputs"].items():
        expected = f"cars-dl_{oid}" if spec["type"] == "download" else f"cars-out_{oid}"
        assert expected in html, oid
    assert "Summarise" in html
    assert "cars-status" in html


def test_program_ui_top_layout_and_override() -> None:
    contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    contract.data["ui"]["layout"] = "top"
    assert "bslib-sidebar-layout" not in str(modules.program_ui("x", contract))
    custom = modules.program_ui("y", contract, ui_override=lambda c: "custom")
    assert "custom" in str(custom)


def test_program_server_is_callable() -> None:
    assert callable(modules.program_server)
