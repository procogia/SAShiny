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

import time
from pathlib import Path

import pytest

import sashiny
from _repo import repo_root
from sashiny import modules

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"

pytest.importorskip("shiny.testserver")

from shiny import App, ui  # noqa: E402
from shiny.testserver import test_server  # noqa: E402


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def _wait_for_run(session: object, timeout: float = 5.0) -> str:
    """Flush until the module's run finishes (extended tasks run off the loop)."""
    deadline = time.monotonic() + timeout
    status = "running..."
    while time.monotonic() < deadline:
        session.flush()  # type: ignore[attr-defined]
        status = session.get_output("mod-status").value  # type: ignore[attr-defined]
        if status != "running...":
            break
        time.sleep(0.05)
    # Flush a few more times so every output card (each its own async render)
    # settles after the result becomes available.
    for _ in range(5):
        session.flush()  # type: ignore[attr-defined]
        time.sleep(0.02)
    return status


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
        status = _wait_for_run(session)
        assert "status: success" in status


def test_module_renders_log() -> None:
    app = _make_app(_minimal_contract())
    with test_server(app) as session:
        session.set_inputs(**{"mod-run": 1})
        _wait_for_run(session)
        log = session.get_output("mod-log")
        assert log.value == "(no log)"


def test_module_reports_invalid_values() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    app = _make_app(contract)
    with test_server(app) as session:
        session.set_inputs(**{"mod-min_msrp": "not-a-number", "mod-ratio": 0.5, "mod-big": 1})
        session.set_inputs(**{"mod-run": 1})
        status = _wait_for_run(session)
        assert "status: error" in status


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
        status = _wait_for_run(session)
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
        status = _wait_for_run(session)
        assert "no recording matches" in status
        assert "No output for this run" in str(session.get_output("mod-out_stats").value)


def test_module_shows_choices_error_before_first_run() -> None:
    # A choices_from load failure must be visible before any Run click (#68).
    contract = sashiny.load(FIX / "contracts" / "valid" / "choice" / "contract.sashiny.yml")

    class BrokenChoices(sashiny.MockEngine):
        def choices(self, contract: sashiny.Contract) -> dict[str, list[dict[str, str]]]:
            raise RuntimeError("SAS unreachable")

    engine = BrokenChoices()
    app_ui = ui.page_fluid(modules.program_ui("mod", contract))

    def server(input, output, session):
        modules.program_server("mod", contract, engine)

    app = App(app_ui, server)
    with test_server(app) as session:
        session.flush()
        status = session.get_output("mod-status").value
        assert "could not read choices" in status
        assert "SAS unreachable" in status


def test_module_card_does_not_stick_on_running_after_error() -> None:
    # After an engine error, an output card must not keep showing "Running..."
    # forever (issue #52); it shows "No output for this run." instead.
    class Failing(sashiny.MockEngine):
        def run(self, contract, values, *, today=None, uploads=None, run_id=None):
            result = sashiny.Result.new(run_id or "r", "error", engine="mock")
            result.metadata["engine_error"] = "boom"
            return result

    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    app_ui = ui.page_fluid(modules.program_ui("mod", contract))

    def server(input, output, session):
        modules.program_server("mod", contract, Failing())

    app = App(app_ui, server)
    with test_server(app) as session:
        session.set_inputs(**{"mod-run": 1})
        _wait_for_run(session)
        card = str(session.get_output("mod-out_log").value)
        assert "Running..." not in card


def test_module_coalesces_run_clicks() -> None:
    # A burst of Run clicks must not queue one engine run per click (issue #49).
    runs: list[int] = []

    class Counting(sashiny.MockEngine):
        def run(self, contract, values, *, today=None, uploads=None, run_id=None):
            runs.append(1)
            time.sleep(0.2)
            return super().run(contract, values, today=today, uploads=uploads, run_id=run_id)

    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    app_ui = ui.page_fluid(modules.program_ui("mod", contract))

    def server(input, output, session):
        modules.program_server("mod", contract, Counting())

    app = App(app_ui, server)
    with test_server(app) as session:
        for i in range(5):
            session.set_inputs(**{"mod-run": i + 1})
        _wait_for_run(session)
        assert len(runs) == 1
