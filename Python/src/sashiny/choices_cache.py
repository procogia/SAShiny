"""``choices_from`` cache (spec ``CONTRACT.md`` §6.4 "Caching"; #130 J3).

Choices are loaded once per engine (an app shares one engine across its
browser sessions) and contract, and reused for ``run.choices_ttl_seconds``
(default 3600; 0 disables the cache). Replacing the SAS session clears it.
"""

from __future__ import annotations

import threading
import time
import weakref
from typing import TYPE_CHECKING, Any

from .recording import contract_sha256

if TYPE_CHECKING:
    from .contract import Contract
    from .engines import Engine

__all__ = ["cached", "clear", "load", "ttl"]

Choices = dict[str, list[dict[str, str]]]

_LOCK = threading.Lock()
_CACHE: weakref.WeakKeyDictionary[Any, dict[str, tuple[float, Choices]]] = (
    weakref.WeakKeyDictionary()
)


def ttl(contract: Contract) -> float:
    """Return the contract's choices time-to-live in seconds (spec §6.4)."""
    return float((contract.data.get("run") or {}).get("choices_ttl_seconds", 3600))


def has_choices_from(contract: Contract) -> bool:
    """Return whether the contract has any ``choices_from`` input."""
    return any("choices_from" in s for s in (contract.data.get("inputs") or {}).values())


def cached(engine: Engine, contract: Contract) -> Choices | None:
    """Return fresh cached choices for ``contract`` on ``engine``, or ``None``."""
    limit = ttl(contract)
    if limit <= 0:
        return None
    key = contract_sha256(contract)
    with _LOCK:
        hit = _CACHE.get(engine, {}).get(key)
        if hit is None:
            return None
        if time.monotonic() - hit[0] > limit:
            del _CACHE[engine][key]
            return None
        return hit[1]


def store(engine: Engine, contract: Contract, value: Choices) -> Choices:
    """Cache ``value`` for ``contract`` on ``engine`` (unless the TTL is 0)."""
    if ttl(contract) > 0:
        with _LOCK:
            _CACHE.setdefault(engine, {})[contract_sha256(contract)] = (time.monotonic(), value)
    return value


def clear(engine: Engine) -> None:
    """Forget every cached choice of ``engine`` (its SAS session was replaced)."""
    with _LOCK:
        _CACHE.pop(engine, None)


def load(engine: Engine, contract: Contract) -> Choices:
    """Return cached choices, or query the engine and cache the result."""
    hit = cached(engine, contract)
    if hit is not None:
        return hit
    return store(engine, contract, engine.choices(contract))
