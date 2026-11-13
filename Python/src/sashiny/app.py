"""App helpers for SAShiny.

``app`` builds a multi-program Shiny app from a list of contracts, using the
Shiny modules and an engine. It is the one-liner entry point for hosting several
SAS programs as tabs in a single app.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract import Contract, default_module_id, load
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

    Raises:
        ValueError: If two contracts resolve to the same module id.

    """
    from shiny import App, ui  # noqa: PLC0415 - optional dependency

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

    app_ui = ui.page_navbar(
        *[
            ui.nav_panel(
                contract.data.get("title", f"Program {i}"),
                program_ui(ids[i], contract),
            )
            for i, contract in enumerate(loaded)
        ],
        title=title,
    )

    def server(input: Any, output: Any, session: Any) -> None:
        for i, contract in enumerate(loaded):
            program_server(ids[i], contract, engine)

    return App(app_ui, server)
