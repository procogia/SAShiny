"""Fail when the R and Python versions or their spec releases drift (CONTRACT.md 11).

Run from the repository root: ``python spec/tools/check_versions.py``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _find(path: str, pattern: str) -> str:
    text = (ROOT / path).read_text(encoding="utf-8")
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        sys.exit(f"check_versions: no match for {pattern!r} in {path}")
    return m.group(1)


def main() -> int:
    """Compare the package versions and the spec releases; return the exit status."""
    found = {
        "spec/CONTRACT.md spec release": _find("spec/CONTRACT.md", r"Spec release: \*\*([0-9.]+)\*\*"),
        "R/R/info.R spec release": _find("R/R/info.R", r'^\.sashiny_spec_release <- "([0-9.]+)"'),
        "Python/src/sashiny/info.py spec release": _find(
            "Python/src/sashiny/info.py", r'^SPEC_RELEASE = "([0-9.]+)"'
        ),
    }
    versions = {
        "R/DESCRIPTION Version": _find("R/DESCRIPTION", r"^Version: (\S+)"),
        "Python __version__": _find("Python/src/sashiny/__init__.py", r'^__version__ = "([^"]+)"'),
    }
    problems = []
    if len(set(found.values())) != 1:
        problems.append("spec releases differ: " + ", ".join(f"{k}={v}" for k, v in found.items()))
    if len(set(versions.values())) != 1:
        problems.append("package versions differ (lockstep): " + ", ".join(f"{k}={v}" for k, v in versions.items()))
    for p in problems:
        print(f"FAIL {p}")
    if not problems:
        print(f"OK version {next(iter(versions.values()))}, spec release {next(iter(found.values()))}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
