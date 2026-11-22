"""Runner for SAShiny.

The runner is a thin orchestration over an engine: it loads a contract, validates
and renders the inputs, submits the wrapper, and collects the outputs into a
:class:`sashiny.result.Result`. It is the layer the Shiny modules and app helpers
call.
"""

from __future__ import annotations

import warnings
from datetime import date
from pathlib import Path
from typing import Any, cast

from . import result_cache
from .contract import Contract, load
from .engines import Engine
from .engines.base import check_engine
from .result import Result

__all__ = ["close", "run"]


def run(  # noqa: PLR0913 - mirrors the engine.run signature
    contract: Contract | str | Path,
    engine: Engine | dict[str, Any] | None,
    values: dict[str, Any] | Engine | None = None,
    *,
    today: date | None = None,
    uploads: dict[str, Any] | None = None,
    run_id: str | None = None,
) -> Result:
    """Run a contract with the given inputs on an engine.

    Args:
        contract: A loaded :class:`Contract`, or a path to a ``*.sashiny.yml``
            file (loaded automatically).
        engine: A :func:`sashiny.connect` engine or a :class:`sashiny.Pool`.
        values: Input values keyed by input id (JSON form, spec §2.1).
            Defaults to the contract's defaults (no values).
        today: The date used to resolve ``"today"``. Defaults to today.
        uploads: Maps dataset input ids to a file path, an ``UploadFile``,
            ``True`` for the input's ``sample`` file, or a pandas DataFrame,
            which is written as CSV (spec §7.1).
        run_id: The run identifier. Defaults to a generated UUID.

    Returns:
        The collected :class:`Result`. With ``run.cache: true`` (spec §6.11) an
        identical earlier ``success``/``warning`` run is returned instead, with
        ``metadata["cache_hit"] = True``.

    Raises:
        TypeError: If ``engine`` is not a live SAS engine or pool.

    Note:
        Before 0.3.1 the order was ``run(contract, values, engine)``. That
        order still works and emits a :class:`DeprecationWarning`.

    """
    if isinstance(values, Engine) and not isinstance(engine, Engine):
        warnings.warn(
            "run(contract, values, engine) is deprecated; pass the engine second: "
            "run(contract, engine, values)",
            DeprecationWarning,
            stacklevel=2,
        )
        engine, values = values, engine
    eng = cast("Engine", engine)
    check_engine(eng)
    if not isinstance(contract, Contract):
        contract = load(contract)
    loaded = contract
    vals = cast("dict[str, Any]", values or {})
    return result_cache.cached_run(
        eng,
        loaded,
        vals,
        lambda: eng.run(loaded, vals, today=today, uploads=uploads, run_id=run_id),
        today=today,
        uploads=uploads,
    )


def close(engine: Engine) -> None:
    """Close an engine or pool, ending every SAS session it holds (safe to repeat)."""
    engine.close()
