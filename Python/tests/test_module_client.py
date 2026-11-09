"""Shiny test client for the SAShiny modules (issue #9).

Uses the open-source Shiny test server (``shiny.testserver.test_server`` +
``TestServerSession``) to drive the ``program_server`` module in-memory and
assert on its rendered outputs. This requires Shiny >= 1.9.1.dev (the test
server landed after 1.9.0); on older Shiny the tests skip.

Run on Linux/CI (or a Daytona VM) where the dev Shiny is installed:

    pip install "git+https://github.com/posit-dev/py-shiny.git"
    pytest tests/test_module_client.py
"""

from __future__ import annotations

from pathlib import Path

import pytest

import sashiny
from sashiny import modules

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"

pytest.importorskip("shiny.testserver")

from shiny import App, ui  # noqa: E402
from shiny.testserver import test_server  # noqa: E402


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def _make_app(contract: sashiny.Contract) -> App:
    """Wrap the program module in a minimal app for in-memory testing."""
    engine = sashiny.MockEngine()

    app_ui = ui.page_fluid(modules.program_ui("mod", contract))

    def server(input, output, session):
        modules.program_server("mod", contract, engine)

    return App(app_ui, server)


def test_module_runs_and_renders_status() -> None:
    app = _make_app(_minimal_contract())
    with test_server(app) as session:
        session.set_inputs(**{"mod-run": 1})
        status = session.get_output("mod-status")
        assert "status: success" in status.value


def test_module_renders_log() -> None:
    app = _make_app(_minimal_contract())
    with test_server(app) as session:
        session.set_inputs(**{"mod-run": 1})
        log = session.get_output("mod-log")
        assert log.value == "(no log)"


def test_module_reports_invalid_values() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    app = _make_app(contract)
    with test_server(app) as session:
        session.set_inputs(**{"mod-min_msrp": "not-a-number", "mod-ratio": 0.5, "mod-big": 1})
        session.set_inputs(**{"mod-run": 1})
        status = session.get_output("mod-status")
        assert "status: error" in status.value
