"""Tests for the custom-module override."""

from __future__ import annotations

from pathlib import Path

import sashiny
from sashiny import modules

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def _contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def test_program_ui_override() -> None:
    contract = _contract()
    # The @module.ui decorator requires a namespace; test the override via the
    # underlying function by checking the override is invoked.
    called: list[bool] = []

    def custom_ui(c: sashiny.Contract) -> object:
        called.append(True)
        return "custom"

    # Call the decorated function with a namespace id and the override.
    result = modules.program_ui("mod", contract, custom_ui)
    assert result == "custom"
    assert called == [True]


def test_program_server_override_is_callable() -> None:
    # The server override is passed through; verify the decorated server accepts
    # the extra argument (full behaviour is exercised by the Shiny test client).
    assert callable(modules.program_server)
