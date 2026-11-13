"""Tests for the app layer."""

from __future__ import annotations

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"


def _contracts() -> list[sashiny.Contract]:
    return [
        sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml"),
        sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml"),
    ]


def test_app_builds_multi_program_app() -> None:
    app = sashiny.app(_contracts(), sashiny.MockEngine())
    assert app is not None


def test_app_accepts_paths() -> None:
    paths = [
        FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml",
        FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml",
    ]
    app = sashiny.app(paths, sashiny.MockEngine())
    assert app is not None
