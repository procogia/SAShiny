"""Tests for the Shiny modules (issue #9)."""

from __future__ import annotations

from pathlib import Path

import sashiny
from sashiny import modules

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def test_input_ui_renders_control() -> None:
    # The @module.ui decorator requires a namespace context; test the underlying
    # input renderer directly instead.
    spec = {"type": "numeric", "label": "N", "default": 1}
    el = modules._input_ui("n", spec)
    assert el is not None


def test_input_ui_renders_each_kind() -> None:
    kinds = [
        {"type": "numeric", "label": "N", "default": 1},
        {"type": "text", "label": "T", "default": "x"},
        {"type": "choice", "label": "C", "choices": ["a", "b"]},
        {"type": "multichoice", "label": "M", "choices": ["a", "b"]},
        {"type": "date", "label": "D"},
        {"type": "daterange", "label": "R"},
        {"type": "dataset", "label": "F"},
    ]
    for spec in kinds:
        assert modules._input_ui("i", spec) is not None


def test_program_server_is_callable() -> None:
    # The server function is decorated; verify it is callable with the expected
    # signature (full behaviour is exercised by the Shiny test client).
    assert callable(modules.program_server)
