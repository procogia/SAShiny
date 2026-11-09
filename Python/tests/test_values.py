"""Conformance tests for value validation and rendering (issue #4).

Reads ``spec/fixtures/values`` and asserts exact macro name/value/order for
``ok`` cases and the exact ``{code, input}`` set for ``invalid`` cases.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

import sashiny

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def _value_files() -> list[Path]:
    return sorted((FIX / "values").glob("*.json"))


def _cases() -> list[tuple[Path, dict]]:
    out: list[tuple[Path, dict]] = []
    for vf in _value_files():
        spec = json.loads(vf.read_text(encoding="utf-8"))
        for case in spec["cases"]:
            out.append((vf, case))
    return out


@pytest.mark.parametrize(
    ("vf", "case"),
    _cases(),
    ids=lambda x: x.stem if isinstance(x, Path) else x["name"],
)
def test_values(vf: Path, case: dict) -> None:
    spec = json.loads(vf.read_text(encoding="utf-8"))
    contract = sashiny.load(FIX / spec["contract"] / "contract.sashiny.yml")
    today = date.fromisoformat(spec["today"])
    macros, issues = sashiny.render_values(
        contract.data,
        case["values"],
        today,
        choices_override=case.get("choices_from"),
        uploads=case.get("uploads"),
    )
    exp = case["expected"]
    if exp["status"] == "ok":
        assert not issues, f"issues={[i.key() for i in issues]} macros={macros}"
        assert list(macros.items()) == list(exp["macros"].items()), (
            f"macros={macros} want={exp['macros']}"
        )
    else:
        want = {(e["code"], e["input"]) for e in exp["errors"]}
        got = {(i.code, i.path) for i in issues}
        assert got == want, f"want {sorted(want)} got {sorted(got)}"
