"""Engine interface for SAShiny.

An engine runs a contract against a SAS backend (or a mock) and returns a
:class:`sashiny.result.Result`. The interface is shared by the mock engine
(record/replay) and the saspy engine (live SAS 9.4 / Viya).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from typing import Any

from ..contract import Contract
from ..result import Result

__all__ = ["Engine"]


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
        uploads: dict[str, bool] | None = None,
        run_id: str | None = None,
    ) -> Result:
        """Run a contract with the given input values.

        Args:
            contract: The loaded contract.
            values: Input values keyed by input id (JSON form, spec §2.1).
            today: The date used to resolve ``"today"``. Defaults to today.
            uploads: Maps dataset input ids to ``True`` when a file was supplied.
            run_id: The run identifier. Defaults to a generated UUID.

        Returns:
            The collected :class:`Result`.

        """
        raise NotImplementedError
