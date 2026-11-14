"""Tests for the app layer."""

from __future__ import annotations

import pytest

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"


def _contracts() -> list[sashiny.Contract]:
    a = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    b = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    # Both fixtures use `program.sas`, so give them distinct explicit ids to
    # avoid the duplicate-module-id error (spec §2).
    a.data["id"] = "minimal"
    b.data["id"] = "numeric"
    return [a, b]


def test_app_builds_multi_program_app() -> None:
    app = sashiny.app(_contracts(), sashiny.MockEngine())
    assert app is not None


def test_app_accepts_paths() -> None:
    paths = [
        FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml",
    ]
    app = sashiny.app(paths, sashiny.MockEngine())
    assert app is not None


def test_app_rejects_duplicate_module_ids() -> None:
    a = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    b = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    # Both derive to `program` from their `program.sas` file name.
    with pytest.raises(ValueError, match="duplicate module id"):
        sashiny.app([a, b], sashiny.MockEngine())


def test_default_module_id_derivation() -> None:
    assert sashiny.default_module_id("Cars Explorer.sas") == "cars_explorer"
    assert sashiny.default_module_id("2nd-report.sas") == "p_2nd_report"
    assert sashiny.default_module_id("Report.SAS") == "report"
    assert sashiny.default_module_id("a" * 40 + ".sas") == "a" * 32


def test_default_module_id_unicode_normalization() -> None:
    # Issue #63: a capital dotted I (U+0130) must lower-case to a plain `i`,
    # not `i` + a combining dot, so the id matches R's `tolower`.
    assert sashiny.default_module_id("\u0130stanbul.sas") == "istanbul"
