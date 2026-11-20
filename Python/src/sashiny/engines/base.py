"""Engine interface for SAShiny.

An engine runs a contract against a live SAS system and returns a
:class:`sashiny.result.Result`. The public engines are the saspy engine (SAS
9.4, SAS Viya, SAS OnDemand for Academics) and pools of it; the offline mock is
an internal test fixture (spec §6.6).
"""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from ..contract import Contract
from ..result import Result

__all__ = ["Engine", "check_engine", "testing"]


def testing() -> bool:
    """Whether the code runs inside the package's pytest suite."""
    return "pytest" in sys.modules and "PYTEST_CURRENT_TEST" in os.environ


def check_engine(engine: Engine) -> Engine:
    """Return ``engine`` if it runs on a live SAS system (spec §6.6).

    The public entry points accept only :class:`sashiny.SaspyEngine` (including
    the in-session :class:`sashiny.ProcPythonEngine`) and :class:`sashiny.Pool`.
    Any other engine (the internal mock, or a custom class that could return
    logs that never came from SAS) is accepted only inside the test suite.

    Raises:
        TypeError: For any other engine outside the test suite.

    """
    from ..pool import Pool  # noqa: PLC0415 - avoid an import cycle
    from .saspy import SaspyEngine  # noqa: PLC0415

    if isinstance(engine, (SaspyEngine, Pool)) or testing():
        return engine
    raise TypeError(
        "engine must come from sashiny.connect(), SaspyEngine or Pool: SAShiny runs "
        "programs only on a live SAS 9.4, SAS Viya or SAS OnDemand for Academics system"
    )


class Engine(ABC):
    """Abstract engine interface.

    Subclasses implement :meth:`run`, which validates and renders the inputs,
    submits the wrapper, and collects the outputs into a :class:`Result`.
    """

    name: str = "engine"
    version: str = "0.0.0"

    @abstractmethod
    def run(
        self,
        contract: Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> Result:
        """Run a contract with the given input values.

        Args:
            contract: The loaded contract.
            values: Input values keyed by input id (JSON form, spec §2.1).
            today: The date used to resolve ``"today"``. Defaults to today.
            uploads: Maps dataset input ids to the supplied file: a path, an
                :class:`sashiny.upload.UploadFile`, or ``True`` for the
                input's ``sample`` file.
            run_id: The run identifier. Defaults to a generated UUID.

        Returns:
            The collected :class:`Result`.

        """
        raise NotImplementedError

    def choices(self, contract: Contract) -> dict[str, list[dict[str, str]]]:
        """Read the choices of ``choices_from`` inputs (spec §6.4).

        Returns:
            Choices keyed by input id, each ``{"value": ..., "label": ...}``.
            Engines without SAS return ``{}``.

        """
        return {}

    def close(self) -> None:  # noqa: B027 - optional hook, a no-op by default
        """Release engine resources (a no-op unless the engine holds a session)."""
