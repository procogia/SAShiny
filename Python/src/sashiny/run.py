"""Runner for SAShiny.

The runner is a thin orchestration over an engine: it loads a contract, validates
and renders the inputs, submits the wrapper, and collects the outputs into a
:class:`sashiny.result.Result`. It is the layer the Shiny modules and app helpers
call, and it is fully testable against the mock engine.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .contract import Contract, load
from .engines import Engine
from .result import Result

__all__ = ["run"]


def run(  # noqa: PLR0913 - mirrors the engine.run signature
    contract: Contract | str | Path,
    values: dict[str, Any],
    engine: Engine,
    *,
    today: date | None = None,
    uploads: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> Result:
    """Run a contract with the given inputs on an engine.

    Args:
        contract: A loaded :class:`Contract`, or a path to a ``*.sashiny.yml``
            file (loaded automatically).
        values: Input values keyed by input id (JSON form, spec §2.1).
        engine: The engine to run on (mock or saspy).
        today: The date used to resolve ``"today"``. Defaults to today.
        uploads: Maps dataset input ids to a file path, an ``UploadFile``, or
            ``True`` for the input's ``sample`` file.
        run_id: The run identifier. Defaults to a generated UUID.

    Returns:
        The collected :class:`Result`.

    """
    if not isinstance(contract, Contract):
        contract = load(contract)
    return engine.run(contract, values, today=today, uploads=uploads, run_id=run_id)
