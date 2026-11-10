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


def _recorded_app(tmp_path: Path) -> tuple[App, sashiny.Contract]:
    """An app whose mock engine replays a recording made by a (fake) live run."""
    pytest.importorskip("pandas")
    from fakesas import FakeSAS  # noqa: PLC0415
    from test_engine_saspy_live import CONTRACT, _fake  # noqa: PLC0415

    (tmp_path / "prog.sas").write_text("data work.stats; run;\n", encoding="utf-8")
    (tmp_path / "adsl.csv").write_text("age,name\n40,Ann\n", encoding="utf-8")
    (tmp_path / "app.sashiny.yml").write_text(CONTRACT, encoding="utf-8")
    contract = sashiny.load(tmp_path / "app.sashiny.yml")
    fake: FakeSAS = _fake()
    live = sashiny.SaspyEngine({}, session_factory=lambda: fake, record_to=tmp_path / "rec")
    live.run(contract, {"min_age": 18, "make": None}, uploads={"adsl": True})
    engine = sashiny.MockEngine(tmp_path / "rec")
    app_ui = ui.page_fluid(modules.program_ui("mod", contract))

    def server(input, output, session):
        modules.program_server("mod", contract, engine)

    return App(app_ui, server), contract


def test_module_replays_recording_into_cards(tmp_path: Path) -> None:
    app, _ = _recorded_app(tmp_path)
    with test_server(app) as session:
        session.set_inputs(**{"mod-min_age": 18, "mod-adsl__sample": True, "mod-run": 1})
        status = session.get_output("mod-status").value
        assert "status: success" in status
        assert "replayed recording" in status
        stats = str(session.get_output("mod-out_stats").value)
        assert "Age (y)" in stats
        assert "Ann" in stats
        assert "dataset WORK.NOPE not found" in str(session.get_output("mod-out_missing").value)
        assert "data:image/png;base64" in str(session.get_output("mod-out_graphs").value)
        assert "SASHINY" not in str(session.get_output("mod-out_log").value)


def test_module_reports_missing_recording(tmp_path: Path) -> None:
    app, _ = _recorded_app(tmp_path)
    with test_server(app) as session:
        session.set_inputs(**{"mod-min_age": 99, "mod-adsl__sample": True, "mod-run": 1})
        status = session.get_output("mod-status").value
        assert "no recording matches" in status
        assert "No output for this run" in str(session.get_output("mod-out_stats").value)
