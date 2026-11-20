"""Exception hierarchy (#130 H5), mirroring the R error classes.

Every error SAShiny raises is a :class:`SashinyError`. Each kind also derives
from the built-in exception it replaces, so existing ``except ValueError`` code
keeps working. Engine runs still return error results and never raise
(spec §6.5); :meth:`sashiny.Result.check` turns a failed result into a
:class:`RunError`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .result import Result

__all__ = [
    "ContractError",
    "DeployError",
    "EngineError",
    "LicenseError",
    "RunError",
    "SashinyError",
    "UploadError",
    "ValuesError",
]


class SashinyError(Exception):
    """Base class of every SAShiny error."""


class ContractError(SashinyError, ValueError):
    """A contract is invalid (names the file and each issue's path)."""

    def __init__(self, message: str, issues: list[Any] | None = None, file: str = "") -> None:
        """Store the message, the issues and the contract file."""
        super().__init__(message)
        self.issues = issues or []
        self.file = file


class ValuesError(SashinyError, ValueError):
    """An argument or value is invalid (outputs, charts, options)."""


class EngineError(SashinyError, TypeError):
    """An engine is not usable (not a live SAS engine, or misconfigured)."""


class LicenseError(SashinyError, RuntimeError):
    """The SAS licence was not acknowledged (spec §6.6)."""


class UploadError(SashinyError, ValueError):
    """An upload failed §7 conversion (reported as ``V014``)."""


class DeployError(SashinyError, ValueError):
    """A deployment target, option or profile is invalid (spec §6.8)."""


class RunError(SashinyError, RuntimeError):
    """A run did not succeed; raised by :meth:`sashiny.Result.check`."""

    def __init__(self, message: str, result: Result) -> None:
        """Store the message and the failed result."""
        super().__init__(message)
        self.result = result
