"""App helpers for SAShiny.

``app`` builds a multi-program Shiny app from a list of contracts, using the
Shiny modules and an engine. It is the one-liner entry point for hosting several
SAS programs as tabs in a single app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .collect import is_paired
from .contract import Contract, default_module_id, load
from .engines import Engine
from .engines.base import check_engine
from .modules import program_server, program_ui
from .publish import on_connect

__all__ = ["app"]


def app(  # noqa: PLR0913 - the §8.6 chart settings are keyword-only options
    contracts: list[Contract | str | Path],
    engine: Engine,
    *,
    title: str = "SAShiny",
    publish: bool = False,
    chart_view: str | dict[str, str] = "sashiny",
    chart_toggle: bool = True,
) -> Any:
    """Build a multi-program Shiny app from a list of contracts.

    Args:
        contracts: A list of :class:`Contract` objects or paths to
            ``*.sashiny.yml`` files (loaded automatically).
        engine: A :func:`sashiny.connect` engine or a :class:`sashiny.Pool`.
        title: The app title.
        publish: Add a "Publish" tab that deploys the app to Posit Connect with
            :func:`sashiny.publish`. Off by default and never shown when the
            app itself runs on Posit Connect.
        chart_view: The default view of paired outputs (spec §8.6), passed to
            every module: `"sashiny"` (default), `"sas"`, or a dict of paired
            output id to view. Each module uses the entries for its outputs.
        chart_toggle: Whether to show the SAS / SAShiny toggles (default `True`).

    Returns:
        A Shiny ``App`` with one tab per contract.

    Raises:
        ValueError: If two contracts resolve to the same module id.
        TypeError: If ``engine`` is not a live SAS engine or pool.

    """
    from shiny import App, reactive, render, ui  # noqa: PLC0415 - optional dependency

    check_engine(engine)
    show_publish = publish and not on_connect()

    loaded = [c if isinstance(c, Contract) else load(c) for c in contracts]

    def _module_id(contract: Contract) -> str:
        return contract.data.get("id") or default_module_id(contract.data["program"])

    # Reject duplicate module ids (spec §2): two tabs sharing a namespace would
    # collide on every input and output id.
    ids = [_module_id(c) for c in loaded]
    seen: dict[str, int] = {}
    for i, mid in enumerate(ids):
        if mid in seen:
            raise ValueError(
                f"duplicate module id {mid!r}: contracts {seen[mid]} and {i} resolve to the same id"
            )
        seen[mid] = i
    views = [_module_views(c, chart_view) for c in loaded]
    if isinstance(chart_view, dict):
        used = {oid for v in views if isinstance(v, dict) for oid in v}
        unknown = [oid for oid in chart_view if oid not in used]
        if unknown:
            raise ValueError(f"chart_view names outputs that are not paired: {', '.join(unknown)}")

    panels = [
        ui.nav_panel(contract.data.get("title", f"Program {i}"), program_ui(ids[i], contract))
        for i, contract in enumerate(loaded)
    ]
    if show_publish:
        panels.append(ui.nav_panel("Publish", _publish_ui()))
    app_ui = ui.page_navbar(*panels, title=title)

    def server(input: Any, output: Any, session: Any) -> None:
        for i, contract in enumerate(loaded):
            program_server(ids[i], contract, engine, chart_view=views[i], chart_toggle=chart_toggle)
        if not show_publish:
            return
        status = reactive.value("")

        @reactive.effect
        @reactive.event(input.sashiny_publish)
        def _publish() -> None:
            from .publish import publish as do_publish  # noqa: PLC0415

            try:
                res = do_publish(
                    input.sashiny_publish_dir(),
                    title=input.sashiny_publish_title() or None,
                    sas_credentials=input.sashiny_publish_creds(),
                    license_ack=bool(input.sashiny_publish_ack()),
                )
            except Exception as exc:  # shown in the panel
                status.set(f"Publish failed: {exc}")
                return
            note = f" Not bundled: {', '.join(res.excluded)}" if res.excluded else ""
            status.set(f"Published {len(res.files)} files.{note}")

        @render.code
        def sashiny_publish_status() -> str:
            return status()

    return App(app_ui, server)


def _module_views(contract: Contract, chart_view: str | dict[str, str]) -> str | dict[str, str]:
    """Return the part of an app-wide `chart_view` that applies to one module."""
    if not isinstance(chart_view, dict):
        return chart_view
    paired = {oid for oid, s in contract.data["outputs"].items() if is_paired(s)}
    return {oid: v for oid, v in chart_view.items() if oid in paired}


def _publish_ui() -> Any:
    from shiny import ui  # noqa: PLC0415 - optional dependency

    return ui.div(
        ui.h4("Publish to Posit Connect"),
        ui.p(
            "Deploys this app with rsconnect-python. Credential files are never bundled. "
            "Set CONNECT_SERVER and CONNECT_API_KEY, or register a server with rsconnect add."
        ),
        ui.input_text("sashiny_publish_dir", "App directory", value=str(Path.cwd())),
        ui.input_text("sashiny_publish_title", "Title", value=""),
        ui.input_radio_buttons(
            "sashiny_publish_creds",
            "SAS credentials on Connect",
            {
                "env": "Send SASHINY_SAS_USER / SASHINY_SAS_PASSWORD from this process",
                "server": "Administrator-managed ~/.authinfo on the server",
            },
        ),
        ui.input_checkbox(
            "sashiny_publish_ack",
            "I confirm that the deployed app runs programs only on a SAS system "
            "I am licensed to use.",
        ),
        ui.input_action_button("sashiny_publish", "Publish", class_="btn-primary"),
        ui.output_code("sashiny_publish_status"),
    )
