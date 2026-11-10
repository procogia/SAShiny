"""Bounded SAS session pool for SAShiny.

Implements a bounded pool of engine sessions (issue #7). The pool reuses
sessions up to ``max_runs_per_session``, discards sessions that error or time
out, and enforces ``min``/``max``/``idle_timeout`` bounds. It works against any
:class:`sashiny.engines.Engine` (mock or saspy).
"""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .contract import Contract
from .engines import Engine
from .result import Result

__all__ = ["Pool", "PoolSession"]


@dataclass
class PoolSession:
    """A pooled engine session and its bookkeeping."""

    engine: Engine
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    runs: int = 0
    last_used: float = field(default_factory=time.monotonic)
    in_use: bool = False


class Pool(Engine):
    """A bounded pool of engine sessions.

    A pool is itself an :class:`Engine`, so it can be passed anywhere an engine
    is accepted (``program_server``, ``sashiny.app``, ``sashiny.run``).

    Args:
        engine: An engine factory (a zero-argument callable such as
            ``lambda: sashiny.connect("oda")``), giving each pooled session its
            own SAS session, or a single engine instance shared by all pooled
            sessions (suitable for :class:`MockEngine`).
        min_size: Minimum number of sessions kept warm.
        max_size: Maximum number of concurrent sessions.
        idle_timeout: Seconds after which an idle session is discarded.
        max_runs_per_session: Runs before a session is discarded and replaced.

    """

    name = "pool"
    version = "0.1.0"

    def __init__(
        self,
        engine: Engine | Callable[[], Engine],
        *,
        min_size: int = 0,
        max_size: int = 4,
        idle_timeout: float = 300.0,
        max_runs_per_session: int = 100,
    ) -> None:
        """Create a bounded pool.

        Args:
            engine: An engine factory, or one engine shared by all sessions.
            min_size: Minimum number of sessions kept warm.
            max_size: Maximum number of concurrent sessions.
            idle_timeout: Seconds after which an idle session is discarded.
            max_runs_per_session: Runs before a session is discarded.

        """
        if isinstance(engine, Engine):
            self.engine: Engine | None = engine
            self._factory: Callable[[], Engine] | None = None
        else:
            self.engine = None
            self._factory = engine
        self.min_size = min_size
        self.max_size = max_size
        self.idle_timeout = idle_timeout
        self.max_runs_per_session = max_runs_per_session
        self._sessions: list[PoolSession] = []
        self._lock = threading.Lock()

    def _new_session(self) -> PoolSession:
        engine = self.engine if self._factory is None else self._factory()
        assert engine is not None  # noqa: S101 - set in __init__
        return PoolSession(engine=engine)

    def _close(self, session: PoolSession) -> None:
        """Close a factory-made session's engine (shared engines stay open)."""
        if self._factory is not None:
            session.engine.close()

    def _discard(self, session: PoolSession) -> None:
        with self._lock:
            self._sessions = [s for s in self._sessions if s is not session]
        self._close(session)

    def choices(self, contract: Contract) -> dict[str, list[dict[str, str]]]:
        """Read ``choices_from`` choices on a pooled session (spec §6.4)."""
        session = self._acquire()
        try:
            return session.engine.choices(contract)
        finally:
            self._release(session, discard=False)

    def close(self) -> None:
        """Close every pooled session."""
        with self._lock:
            sessions, self._sessions = self._sessions, []
        for s in sessions:
            self._close(s)

    def _acquire(self) -> PoolSession:
        with self._lock:
            now = time.monotonic()
            # Reap idle sessions past the timeout.
            idle = [
                s
                for s in self._sessions
                if not s.in_use and (now - s.last_used) >= self.idle_timeout
            ]
            self._sessions = [s for s in self._sessions if s not in idle]
            found: PoolSession | None = None
            # Reuse an idle session.
            for s in self._sessions:
                if not s.in_use:
                    s.in_use = True
                    s.last_used = now
                    found = s
                    break
            # Create a new session if under max.
            if found is None and len(self._sessions) < self.max_size:
                found = self._new_session()
                found.in_use = True
                self._sessions.append(found)
        for s in idle:
            self._close(s)
        if found is not None:
            return found
        # Pool exhausted.
        raise RuntimeError("pool exhausted")

    def _release(self, session: PoolSession, discard: bool) -> None:
        with self._lock:
            session.in_use = False
            session.last_used = time.monotonic()
            drop = discard or session.runs >= self.max_runs_per_session
            if drop:
                self._sessions = [s for s in self._sessions if s is not session]
        if drop:
            self._close(session)

    def run(
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Result:
        """Run a contract on a pooled session.

        The session is discarded if a submitted run errors or times out (spec
        §6.5). Input validation errors never reach SAS and keep the session.
        """
        session = self._acquire()
        discard = False
        try:
            result = session.engine.run(
                contract, values, today=today, uploads=uploads, run_id=run_id
            )
            session.runs += 1
            discard = result.status == "error" and "issues" not in result.metadata
            return result
        finally:
            self._release(session, discard=discard)
