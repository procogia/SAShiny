"""SAShiny Lisbon demo app (Python).

A multi-tab Shiny app (General / Pharma / AML) that runs the three example
contracts through the mock engine (offline mode). The connection-profile picker
and live/offline toggle are present; live SAS is stubbed until the saspy engine
(issue #6) and live SAS reports (issue #11) land.

Run from the repository root:

    cd Python && uv run --with shiny python examples/demo/app.py
"""

from __future__ import annotations

from pathlib import Path

from shiny import App, Inputs, Outputs, Session, reactive, ui

import sashiny
from sashiny import modules

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"

TRACKS = {
    "General": EXAMPLES / "general" / "cars_explorer.sashiny.yml",
    "Pharma": EXAMPLES / "pharma" / "ae_summary.sashiny.yml",
    "AML": EXAMPLES / "aml" / "cash_aggregation_tuning.sashiny.yml",
}

PROFILES = ["Offline", "ODA", "ProCogia Viya", "ProCogia 9.4"]


def _load_contracts() -> dict[str, sashiny.Contract]:
    return {name: sashiny.load(path) for name, path in TRACKS.items()}


app_ui = ui.page_navbar(
    ui.nav_panel(
        "About",
        ui.markdown(
            "SAShiny demo: unchanged SAS programs as the server of a Shiny app. "
            "Select a track, choose a connection profile, set inputs, and press Run."
        ),
    ),
    ui.nav_panel("General", modules.program_ui(_load_contracts()["General"])),
    ui.nav_panel("Pharma", modules.program_ui(_load_contracts()["Pharma"])),
    ui.nav_panel("AML", modules.program_ui(_load_contracts()["AML"])),
    title="SAShiny demo",
    sidebar=ui.sidebar(
        ui.input_select("profile", "Connection profile", PROFILES, selected="Offline"),
        ui.input_switch("live", "Live SAS", value=False),
        ui.markdown("Live SAS requires the saspy engine (issue #6)."),
    ),
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """Wire the demo server: run each track through the mock engine."""
    contracts = _load_contracts()

    @reactive.calc
    def engine() -> sashiny.Engine:
        # Offline mode uses the mock engine; live SAS is stubbed until #6.
        return sashiny.MockEngine()

    modules.program_server("general", contracts["General"], engine())
    modules.program_server("pharma", contracts["Pharma"], engine())
    modules.program_server("aml", contracts["AML"], engine())


app = App(app_ui, server)
