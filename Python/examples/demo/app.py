"""SAShiny Lisbon demo app skeleton (Python).

A minimal multi-tab Shiny app that loads the three example contracts
(general / pharma / aml) and renders a placeholder UI. The "Run" action
validates the inputs and shows the rendered macro values, standing in for the
mock engine until the full engine and Shiny modules land (issues #5, #9).

Run from the repository root:

    cd Python && uv run --with shiny python examples/demo/app.py

The app imports without saspy; live SAS is not required.
"""

from __future__ import annotations

from pathlib import Path

from shiny import App, Inputs, Outputs, Session, render, ui

import sashiny

REPO = Path(__file__).resolve().parents[3]
EXAMPLES = REPO / "examples"

TRACKS = {
    "General": EXAMPLES / "general" / "cars_explorer.sashiny.yml",
    "Pharma": EXAMPLES / "pharma" / "ae_summary.sashiny.yml",
    "AML": EXAMPLES / "aml" / "cash_aggregation_tuning.sashiny.yml",
}


def _load_contracts() -> dict[str, sashiny.Contract]:
    return {name: sashiny.load(path) for name, path in TRACKS.items()}


def _input_ui(iid: str, spec: dict) -> object:
    """Render a placeholder input control for one contract input."""
    kind = spec["type"]
    label = spec.get("label", iid)
    if kind == "numeric":
        return ui.input_numeric(iid, label, spec.get("default", 0))
    if kind in ("text", "choice"):
        return ui.input_text(iid, label, spec.get("default", ""))
    if kind == "multichoice":
        choices = [c if isinstance(c, str) else c["value"] for c in spec.get("choices", [])]
        return ui.input_checkbox_group(iid, label, choices=choices)
    if kind in ("date", "daterange"):
        return ui.input_text(iid, label, "")
    if kind == "dataset":
        return ui.input_file(iid, label)
    return ui.input_text(iid, label, "")


def _track_ui(name: str, contract: sashiny.Contract) -> object:
    inputs = contract.data.get("inputs") or {}
    controls = [_input_ui(iid, spec) for iid, spec in inputs.items()]
    return ui.nav_panel(
        name,
        ui.h3(contract.data.get("title", name)),
        *controls,
        ui.input_action_button("run", "Run", class_="btn-primary"),
        ui.output_text_verbatim("result"),
    )


app_ui = ui.page_navbar(
    ui.nav_panel(
        "About",
        ui.markdown(
            "SAShiny demo: unchanged SAS programs as the server of a Shiny app. "
            "Select a track, set inputs, and press Run."
        ),
    ),
    *[_track_ui(name, contract) for name, contract in _load_contracts().items()],
    title="SAShiny demo",
)


def server(input: Inputs, output: Outputs, session: Session) -> None:
    """Wire the demo server: validate inputs and show rendered macros."""
    contracts = _load_contracts()

    @output
    @render.text
    def result() -> str:
        # Determine the active track from the nav panel (simplified: use the
        # first track whose inputs are present). The full app will track the
        # active tab explicitly.
        for _name, contract in contracts.items():
            inputs = contract.data.get("inputs") or {}
            values = {iid: input[iid]() for iid in inputs if iid in input}
            if values:
                macros, issues = sashiny.render_values(contract.data, values)
                if issues:
                    return "\n".join(f"{i.code} {i.path} {i.message}" for i in issues)
                return "\n".join(f"{k} = {v}" for k, v in macros.items())
        return "Set inputs and press Run."


app = App(app_ui, server)
