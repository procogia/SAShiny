"""Additional edge-case tests to close coverage gaps."""

from __future__ import annotations

from datetime import date

import pytest

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def test_render_values_v005_pattern_mismatch() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "text" / "contract.sashiny.yml")
    _macros, issues = sashiny.render_values(contract.data, {"study_id": "abc-123"}, TODAY)
    assert any(i.code == "V005" for i in issues)


def test_mock_engine_save_recording_requires_dir() -> None:
    engine = sashiny.MockEngine()  # no recordings_dir
    contract = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    with pytest.raises(ValueError, match="recordings_dir"):
        engine.save_recording(contract, {}, {"status": "success"})
