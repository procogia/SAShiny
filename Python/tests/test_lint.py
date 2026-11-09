"""Tests for the lint layer (issue #5, §10)."""

from __future__ import annotations

from pathlib import Path

import sashiny

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def test_lint_returns_empty_for_now() -> None:
    # The lint layer is a stub (§10); it returns no findings until the full
    # program-scanning implementation lands.
    data = {"sashiny": 1, "program": "x.sas", "title": "t", "outputs": {"log": {"type": "log"}}}
    assert sashiny.lint(data, "proc print data=sashelp.class; run;") == []
