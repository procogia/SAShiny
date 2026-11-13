"""Shared test helpers for locating the repository/sdist root.

The conformance tests read the shared fixtures from ``spec/fixtures`` and the
demo inputs from ``examples/``. In the repository these live two levels above
``tests/`` (``Python/tests/``); in an extracted source distribution they live
one level above (``sashiny-x.y.z/tests/``). ``repo_root()`` finds the directory
that actually contains ``spec/fixtures`` so the same tests run in both layouts.
"""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    """Return the directory containing ``spec/fixtures`` and ``examples/``."""
    here = Path(__file__).resolve()
    for parent in (here.parents[1], here.parents[2], here.parents[3]):
        if (parent / "spec" / "fixtures").is_dir():
            return parent
    return here.parents[2]
