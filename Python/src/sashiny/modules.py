"""Shiny modules for SAShiny (issue #9).

``program_ui`` / ``program_server`` generate a UI from a contract and run it
through an engine, collecting tables, plots, HTML, log and downloads. The
auto-generated UI can be overridden with custom modules.
"""

from __future__ import annotations

from typing import Any

from shiny import Inputs, Outputs, Session, module, reactive, render, ui
from shiny.ui import TagChild

from .contract import Contract
from .engines import Engine

__all__ = ["program_server", "program_ui"]


def _input_ui(iid: str, spec: dict[str, Any]) -> TagChild:  # noqa: PLR0911 - switch over input types
    """Render a Shiny input control for one contract input."""
    kind = spec["type"]
    label = spec.get("label", iid)
    if kind == "numeric":
        return ui.input_numeric(iid, label, spec.get("default", 0))
    if kind == "text":
        return ui.input_text(iid, label, spec.get("default", ""))
    if kind == "choice":
        choices = [c if isinstance(c, str) else c["value"] for c in spec.get("choices", [])]
        return ui.input_select(iid, label, choices=choices)
    if kind == "multichoice":
        choices = [c if isinstance(c, str) else c["value"] for c in spec.get("choices", [])]
        return ui.input_checkbox_group(iid, label, choices=choices)
    if kind == "date":
        return ui.input_date(iid, label)
    if kind == "daterange":
        return ui.input_date_range(iid, label)
    if kind == "dataset":
        return ui.input_file(iid, label)
    return ui.input_text(iid, label, "")


@module.ui
def program_ui(
    contract: Contract,
    ui_override: Any | None = None,
) -> TagChild:
    """Generate the UI for a SAS program module.

    Args:
        contract: The loaded contract.
        ui_override: An optional callable ``(contract) -> TagChild`` that
            replaces the auto-generated UI.

    """
    if ui_override is not None:
        return ui_override(contract)  # type: ignore[no-any-return]
    inputs = contract.data.get("inputs") or {}
    controls = [_input_ui(iid, spec) for iid, spec in inputs.items()]
    return ui.TagList(
        *controls,
        ui.input_action_button("run", contract.data.get("ui", {}).get("run_label", "Run")),
        ui.hr(),
        ui.output_text_verbatim("status"),
        ui.output_text_verbatim("log"),
        ui.output_table("table"),
        ui.output_ui("plots"),
        ui.output_ui("html"),
        ui.output_ui("downloads"),
    )


@module.server
def program_server(  # noqa: PLR0913, PLR0917 - Shiny module signature + override
    input: Inputs,
    output: Outputs,
    session: Session,
    contract: Contract,
    engine: Engine,
    server_override: Any | None = None,
) -> dict[str, Any]:
    """Serve a SAS program module (run the contract and render outputs).

    Args:
        input: Shiny inputs.
        output: Shiny outputs.
        session: Shiny session.
        contract: The loaded contract.
        engine: The engine to run on.
        server_override: An optional callable ``(input, output, session,
            contract, engine)`` that replaces the auto-generated server.

    """
    if server_override is not None:
        return server_override(input, output, session, contract, engine)  # type: ignore[no-any-return]
    inputs = contract.data.get("inputs") or {}

    @reactive.calc
    @reactive.event(input.run)
    def result() -> Any:
        values = {iid: input[iid]() for iid in inputs}
        return engine.run(contract, values)

    @output
    @render.text
    def status() -> str:
        r = result()
        lines = [f"status: {r.status}", f"run_id: {r.run_id}"]
        sas = r.metadata.get("sas_version", "")
        if sas:
            lines.append(f"SAS: {sas}")
        return "\n".join(lines)

    @output
    @render.text
    def log() -> str:
        r = result()
        return r.log or "(no log)"

    @output
    @render.table
    def table() -> object:
        r = result()
        tbl = r.outputs.get("table")
        if tbl is None:
            return None
        return {"columns": tbl.columns, "rows": tbl.rows}

    @output
    @render.ui
    def plots() -> TagChild | None:
        r = result()
        plots = r.outputs.get("plot")
        if not plots:
            return None
        return ui.TagList(*[ui.img(src=f"data:image/png;base64,{p}") for p in plots])

    @output
    @render.ui
    def html() -> TagChild | None:
        r = result()
        html = r.outputs.get("html")
        return ui.HTML(html) if html else None

    @output
    @render.ui
    def downloads() -> TagChild | None:
        r = result()
        dl = r.outputs.get("download")
        if not dl:
            return None
        return ui.TagList(*[ui.download_button(f"dl_{n}", n) for n in dl])

    return {
        "result": result,
        "status": reactive.calc(lambda: result().status),
        "log": reactive.calc(lambda: result().log),
    }
