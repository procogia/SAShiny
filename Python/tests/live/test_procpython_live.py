"""Live parity of the PROC PYTHON engine against saspy (opt-in, QA only).

Run ``tests/live/procpython/probe.sas`` in a SAS Viya job first, copy the
``sashiny_parity_*.json`` files it writes to a local folder, then:

    SASHINY_LIVE=1 SASHINY_PROFILE=viya SASHINY_PROCPYTHON_OUT=<folder> \
        pytest tests/live -k procpython

Each output of the in-session run must match the same contract run through saspy.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import sashiny
from _repo import repo_root

pytestmark = pytest.mark.live
FIX = repo_root() / "spec" / "fixtures" / "contracts" / "valid"


@pytest.mark.parametrize("name", ["minimal", "outputs"])
def test_procpython_matches_saspy(name: str, live_engine: sashiny.SaspyEngine) -> None:
    folder = os.environ.get("SASHINY_PROCPYTHON_OUT")
    if not folder:
        pytest.skip("set SASHINY_PROCPYTHON_OUT to the probe.sas output folder")
    inside = json.loads((Path(folder) / f"sashiny_parity_{name}.json").read_text(encoding="utf-8"))
    outside = sashiny.run(FIX / name / "contract.sashiny.yml", {}, live_engine).outputs
    assert sorted(inside) == sorted(outside)
    for oid, value in outside.items():
        if isinstance(value, dict) and "rows" in value:
            assert inside[oid]["rows"] == json.loads(json.dumps(value["rows"], default=str)), oid
