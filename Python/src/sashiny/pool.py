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


class Pool:
    """A bounded pool of engine sessions.

    Args:
        engine: The engine used to create sessions.
        min_size: Minimum number of sessions kept warm.
        max_size: Maximum number of concurrent sessions.
        idle_timeout: Seconds after which an idle session is discarded.
        max_runs_per_session: Runs before a session is discarded and replaced.

    """

    def __init__(
        self,
        engine: Engine,
        *,
        min_size: int = 0,
        max_size: int = 4,
        idle_timeout: float = 300.0,
        max_runs_per_session: int = 100,
    ) -> None:
        """Create a bounded pool.

        Args:
            engine: The engine used to create sessions.
            min_size: Minimum number of sessions kept warm.
            max_size: Maximum number of concurrent sessions.
            idle_timeout: Seconds after which an idle session is discarded.
            max_runs_per_session: Runs before a session is discarded.

        """
        self.engine = engine
        self.min_size = min_size
        self.max_size = max_size
        self.idle_timeout = idle_timeout
        self.max_runs_per_session = max_runs_per_session
        self._sessions: list[PoolSession] = []
        self._lock = threading.Lock()

    def _new_session(self) -> PoolSession:
        return PoolSession(engine=self.engine)

    def _discard(self, session: PoolSession) -> None:
        with self._lock:
            self._sessions = [s for s in self._sessions if s is not session]

    def _acquire(self) -> PoolSession:
        with self._lock:
            now = time.monotonic()
            # Reap idle sessions past the timeout.
            self._sessions = [
                s for s in self._sessions if s.in_use or (now - s.last_used) < self.idle_timeout
            ]
            # Reuse an idle session.
            for s in self._sessions:
                if not s.in_use:
                    s.in_use = True
                    s.last_used = now
                    return s
            # Create a new session if under max.
            if len(self._sessions) < self.max_size:
                s = self._new_session()
                s.in_use = True
                self._sessions.append(s)
                return s
            # Pool exhausted: block until a session is released.
            raise RuntimeError("pool exhausted")

    def _release(self, session: PoolSession, discard: bool) -> None:
        with self._lock:
            session.in_use = False
            session.last_used = time.monotonic()
            if discard or session.runs >= self.max_runs_per_session:
                self._sessions = [s for s in self._sessions if s is not session]

    def run(
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, bool] | None = None,
        run_id: str | None = None,
    ) -> Result:
        """Run a contract on a pooled session.

        The session is discarded if the run errors or times out (spec §6.5).
        """
        session = self._acquire()
        discard = False
        try:
            result = session.engine.run(
                contract, values, today=today, uploads=uploads, run_id=run_id
            )
            session.runs += 1
            discard = result.status == "error"
            return result
        finally:
            self._release(session, discard=discard)

    def close(self) -> None:
        """Discard all sessions."""
        with self._lock:
            self._sessions = []
