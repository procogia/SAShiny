"""A parent filter panel drives the cars_explorer contract (CONTRACT.md §6.10).

The module's own origin control is hidden; its other inputs stay in the UI.
Runs on SAS OnDemand for Academics. Set ``SASHINY_LICENSE_ACK=true`` to confirm
you are licensed to use it (CONTRACT.md §6.6), then run
``shiny run examples/parent-filter/app.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

from shiny import App, module, reactive, ui

import sashiny
from sashiny import modules

HERE = Path(__file__).parent
contract = sashiny.load(HERE.parent / "general" / "cars_explorer.sashiny.yml")
contract.data.setdefault("ui", {})["auto_run"] = True
engine = sashiny.connect("oda", license_ack=os.environ.get("SASHINY_LICENSE_ACK") == "true")


@module.ui
def filter_ui() -> ui.TagChild:
    """Return the parent filter panel."""
    return ui.input_checkbox_group(
        "origins",
        "Origin (parent filter)",
        ["Asia", "Europe", "USA"],
        selected=["Asia", "Europe", "USA"],
        inline=True,
    )


@module.server
def filter_server(input, output, session):  # type: ignore[no-untyped-def]
    """Return the filter as a reactive dict of contract input values."""
    return reactive.calc(lambda: {"origins": list(input.origins() or [])})


app_ui = ui.page_fluid(
    ui.h2("Cars explorer driven by a parent filter"),
    filter_ui("filter"),
    modules.program_ui("cars", contract),
)


def server(input, output, session):  # type: ignore[no-untyped-def]
    """Wire the filter's values into the program module."""
    values = filter_server("filter")
    modules.program_server("cars", contract, engine, values=values, hide_inputs=True)


app = App(app_ui, server)
