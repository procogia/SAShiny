"""App helpers for SAShiny.

``app`` builds a multi-program Shiny app from a list of contracts, using the
Shiny modules and an engine. It is the one-liner entry point for hosting several
SAS programs as tabs in a single app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import Contract, load
from .engines import Engine
from .modules import program_server, program_ui

__all__ = ["app"]


def app(
    contracts: list[Contract | str | Path],
    engine: Engine,
    *,
    title: str = "SAShiny",
) -> Any:
    """Build a multi-program Shiny app from a list of contracts.

    Args:
        contracts: A list of :class:`Contract` objects or paths to
            ``*.sashiny.yml`` files (loaded automatically).
        engine: The engine to run each program on (mock or saspy).
        title: The app title.

    Returns:
        A Shiny ``App`` with one tab per contract.

    """
    from shiny import App, ui  # noqa: PLC0415 - optional dependency

    loaded = [c if isinstance(c, Contract) else load(c) for c in contracts]

    def _module_id(i: int, contract: Contract) -> str:
        return contract.data.get("id") or f"program_{i}"

    app_ui = ui.page_navbar(
        *[
            ui.nav_panel(
                contract.data.get("title", f"Program {i}"),
                program_ui(_module_id(i, contract), contract),
            )
            for i, contract in enumerate(loaded)
        ],
        title=title,
    )

    def server(input: Any, output: Any, session: Any) -> None:
        for i, contract in enumerate(loaded):
            program_server(_module_id(i, contract), contract, engine)

    return App(app_ui, server)
