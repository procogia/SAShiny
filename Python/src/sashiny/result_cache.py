"""Opt-in result cache (spec ``CONTRACT.md`` §6.11; #130 J5).

With ``run.cache: true`` a run whose contract, program and rendered inputs match
an earlier ``success`` or ``warning`` run reuses that result for
``run.cache_ttl_seconds``. The default is off. The cache is per process and
shared by every engine and pool; the in-memory store is an LRU of 100 entries
and can be replaced with :func:`set_store` (for example by an external cache).
"""

from __future__ import annotations

import copy
import hashlib
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Protocol

from . import choices_cache
from .engines._mock import resolve_files
from .recording import contract_sha256, program_sha256, upload_key_parts
from .upload import UploadError
from .values import render_values

if TYPE_CHECKING:
    from pathlib import Path

    from .contract import Contract
    from .engines import Engine
    from .result import Result

__all__ = [
    "LRUStore",
    "ResultStore",
    "cached_run",
    "clear",
    "enabled",
    "get_store",
    "key_text",
    "set_store",
]

CACHEABLE = frozenset({"success", "warning"})


class ResultStore(Protocol):
    """A result store: replace the in-memory default with :func:`set_store`."""

    def get(self, key: str) -> tuple[Result, float] | None:
        """Return ``(result, stored_at)`` (epoch seconds) for ``key``, or ``None``."""

    def set(self, key: str, result: Result, stored_at: float) -> None:
        """Store ``result`` under ``key``."""

    def delete(self, key: str) -> None:
        """Remove ``key`` if present."""

    def clear(self) -> None:
        """Remove every entry."""


class LRUStore:
    """In-memory, thread-safe least-recently-used store.

    Args:
        max_entries: The most results kept; the least recently used is evicted.

    """

    def __init__(self, max_entries: int = 100) -> None:
        """Create an empty store holding at most ``max_entries`` results."""
        if max_entries < 1:
            raise ValueError("max_entries must be at least 1")
        self.max_entries = max_entries
        self._data: OrderedDict[str, tuple[Result, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> tuple[Result, float] | None:
        """Return ``(result, stored_at)`` for ``key`` and mark it recently used."""
        with self._lock:
            hit = self._data.get(key)
            if hit is not None:
                self._data.move_to_end(key)
            return hit

    def set(self, key: str, result: Result, stored_at: float) -> None:
        """Store ``result``, evicting the least recently used entry when full."""
        with self._lock:
            self._data[key] = (result, stored_at)
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def delete(self, key: str) -> None:
        """Remove ``key`` if present."""
        with self._lock:
            self._data.pop(key, None)

    def clear(self) -> None:
        """Remove every entry."""
        with self._lock:
            self._data.clear()

    def __len__(self) -> int:
        """Return the number of stored results."""
        return len(self._data)


_STORE: ResultStore = LRUStore()


def get_store() -> ResultStore:
    """Return the process-wide result store."""
    return _STORE


def set_store(store: ResultStore | None) -> ResultStore:
    """Replace the process-wide store (``None`` restores a fresh in-memory LRU).

    Returns:
        The previous store.

    """
    global _STORE  # noqa: PLW0603 - one process-wide store, by design (§6.11)
    previous = _STORE
    _STORE = store if store is not None else LRUStore()
    return previous


def clear() -> None:
    """Remove every cached result."""
    _STORE.clear()


def enabled(contract: Contract) -> bool:
    """Return whether the contract opts in with ``run.cache: true``."""
    return bool((contract.data.get("run") or {}).get("cache", False))


def ttl(contract: Contract) -> float:
    """Return ``run.cache_ttl_seconds`` (default 3600)."""
    return float((contract.data.get("run") or {}).get("cache_ttl_seconds", 3600))


def key_text(
    contract_sha: str,
    program_sha: str,
    macros: list[tuple[str, str]],
    uploads: list[tuple[str, str]],
) -> str:
    """Return the §6.11 cache key text."""
    lines = ["sashiny-cache-key 1", f"contract {contract_sha}", f"program {program_sha}"]
    lines += [f"macro {n}={v}" for n, v in macros]
    lines += [f"upload {i} {h}" for i, h in uploads]
    return "\n".join(lines) + "\n"


def _key(
    engine: Engine,
    contract: Contract,
    values: dict[str, Any],
    today: date,
    uploads: dict[str, Any] | None,
) -> str | None:
    """Return the cache key, or ``None`` when the run must bypass the cache."""
    found = getattr(contract, "cached_choices", None)
    if found is None and choices_cache.has_choices_from(contract):
        found = choices_cache.cached(engine, contract)
        if found is None:
            # The rendered values depend on choices not loaded yet.
            return None
    override = {k: [c["value"] for c in v] for k, v in (found or {}).items()}
    flags = {k: bool(v) for k, v in (uploads or {}).items()}
    macros, issues = render_values(
        contract.data, values, today, choices_override=override or None, uploads=flags
    )
    if issues:
        return None
    try:
        files: dict[str, Path] = resolve_files(contract, uploads)
        parts = upload_key_parts(contract, files)
    except (UploadError, OSError):
        return None
    text = key_text(
        contract_sha256(contract), program_sha256(contract), list(macros.items()), parts
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def lookup(
    engine: Engine,
    contract: Contract,
    values: dict[str, Any],
    *,
    today: date | None = None,
    uploads: dict[str, Any] | None = None,
) -> tuple[str | None, Result | None]:
    """Return ``(key, hit)``; ``key`` is ``None`` when the run bypasses the cache."""
    if not enabled(contract):
        return None, None
    key = _key(engine, contract, values, today or date.today(), uploads)
    if key is None:
        return None, None
    hit = _STORE.get(key)
    if hit is None:
        return key, None
    result, stored_at = hit
    if time.time() - stored_at > ttl(contract):
        _STORE.delete(key)
        return key, None
    out = copy.deepcopy(result)
    out.metadata["cache_hit"] = True
    out.metadata["cached_at"] = (
        datetime.fromtimestamp(stored_at, timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )
    return key, out


def store(key: str | None, result: Result) -> Result:
    """Store ``result`` under ``key`` when cacheable; return ``result``."""
    if key is not None and result.status in CACHEABLE:
        _STORE.set(key, copy.deepcopy(result), time.time())
    return result


def cached_run(  # noqa: PLR0913 - mirrors the engine.run signature
    engine: Engine,
    contract: Contract,
    values: dict[str, Any],
    run: Callable[[], Result],
    *,
    today: date | None = None,
    uploads: dict[str, Any] | None = None,
) -> Result:
    """Return a cached result for this run, or call ``run()`` and cache its result."""
    key, hit = lookup(engine, contract, values, today=today, uploads=uploads)
    if hit is not None:
        return hit
    return store(key, run())
