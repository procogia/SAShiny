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
        values: Input values keyed by input id (JSON form, spec §2.1). An
            input not in ``values`` takes the contract's ``default`` (``"today"``
            resolved against ``today``), as when the app starts (spec §6.12); a
            supplied ``None`` makes the input absent. Defaults to ``None``: every
            input at its default.
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
    today = today or date.today()
    vals = _with_defaults(loaded, cast("dict[str, Any] | None", values), today)
    return result_cache.cached_run(
        eng,
        loaded,
        vals,
        lambda: eng.run(loaded, vals, today=today, uploads=uploads, run_id=run_id),
        today=today,
        uploads=uploads,
    )


def _with_defaults(
    contract: Contract, values: dict[str, Any] | None, today: date
) -> dict[str, Any]:
    """Fill the inputs ``values`` does not supply with the contract's defaults (spec §6.12).

    Dataset inputs and inputs without a ``default`` are left out, and ``"today"``
    in a ``date``/``daterange`` default becomes ``today`` in ISO form, so the
    result is in the JSON form of spec §2.1. An id that ``values`` supplies,
    even as ``None``, keeps the supplied value.
    """
    supplied = values or {}
    iso = today.isoformat()
    out: dict[str, Any] = {}
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if spec["type"] == "dataset" or "default" not in spec or iid in supplied:
            continue
        default = spec["default"]
        if isinstance(default, list):
            default = list(default)
        if spec["type"] in {"date", "daterange"}:
            if isinstance(default, list):
                default = [iso if x == "today" else x for x in default]
            elif default == "today":
                default = iso
        out[iid] = default
    out.update(supplied)
    return out


def close(engine: Engine) -> None:
    """Close an engine or pool, ending every SAS session it holds (safe to repeat)."""
    engine.close()
