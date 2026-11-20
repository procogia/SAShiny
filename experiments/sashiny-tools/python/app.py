"""shinychat demo: a chat model calls the cars_explorer contract as a tool.

Needs ``chatlas``, ``shiny``, an LLM API key (for example ``OPENAI_API_KEY``) and a
licensed SAS system; set ``SASHINY_LICENSE_ACK=true`` to confirm the licence. The
mock engine is a test fixture and is only used by ``tests/``.

Run with ``shiny run experiments/sashiny-tools/python/app.py``.
"""

from __future__ import annotations

import os
from pathlib import Path

import chatlas
from sashiny_tools import as_tool
from shiny import App, ui

import sashiny

ROOT = Path(__file__).resolve().parents[3]
contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
engine = sashiny.connect(sashiny.oda(), license_ack=os.environ.get("SASHINY_LICENSE_ACK") == "true")

app_ui = ui.page_fillable(ui.chat_ui("chat"))


def server(input, output, session):  # type: ignore[no-untyped-def]
    """Register the contract tool on a chat and stream replies."""
    chat = chatlas.ChatOpenAI(
        system_prompt=(
            "Answer questions about car prices by calling the cars_explorer tool. "
            "Never write SAS code. Quote the run_id of every run you use."
        )
    )
    chat.register_tool(as_tool(contract, engine))
    chat_ui = ui.Chat("chat")

    @chat_ui.on_user_submit
    async def _reply(user_input: str) -> None:
        await chat_ui.append_message_stream(await chat.stream_async(user_input))


app = App(app_ui, server)
