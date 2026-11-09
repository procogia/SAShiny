"""Conformance tests for wrapper generation (issue #4).

Reads ``spec/fixtures/wrapper`` and asserts byte-exact ``expected_reset.sas``
and ``expected_main.sas`` output.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import sashiny

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def _wrapper_dirs() -> list[Path]:
    return sorted((FIX / "wrapper").iterdir())


@pytest.mark.parametrize("d", _wrapper_dirs(), ids=lambda p: p.name)
def test_wrapper(d: Path) -> None:
    contract = sashiny.load(d / "contract.sashiny.yml")
    case = json.loads((d / "case.json").read_text(encoding="utf-8"))
    today = date.fromisoformat(case["today"])
    issues = sashiny.validate(contract, today)
    assert not issues, str([i.key() for i in issues])
    macros, vissues = sashiny.render_values(
        contract.data, case["values"], today, uploads=case.get("uploads")
    )
    assert not vissues, str([i.key() for i in vissues])
    reset_enabled = (contract.data.get("run") or {}).get("reset_work", True)
    reset_file = d / "expected_reset.sas"
    assert reset_file.exists() == reset_enabled
    if reset_enabled and reset_file.exists():
        assert sashiny.reset_code(contract.data) == reset_file.read_text(encoding="utf-8")
    program = (d / contract.data["program"]).read_bytes()
    got = sashiny.wrapper_code(contract.data, macros, program)
    want = (d / "expected_main.sas").read_text(encoding="utf-8")
    assert got == want
