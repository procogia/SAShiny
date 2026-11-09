"""Advisory lint for SAShiny (spec §10).

Reports program-vs-contract consistency findings (``L001``-``L005``). These are
advisory, not errors. The full implementation scans the SAS program text; this
module currently provides the interface and will be completed in a later phase.
"""

from __future__ import annotations

from typing import Any

from .contract import Issue

__all__ = ["lint"]


def lint(data: dict[str, Any], program_text: str) -> list[Issue]:
    """Return advisory lint findings for a contract and its program text.

    Args:
        data: The parsed contract data.
        program_text: The decoded SAS program text.

    Returns:
        A list of :class:`Issue` objects with ``L0xx`` codes. Empty when no
        findings are detected.

    """
    del data, program_text  # not yet implemented
    return []
