"""Live SAS suite for the Lisbon demo (``SASHINY_LIVE=1``).

Runs every scenario in ``examples/demo-scenarios.yml`` against real SAS with
the real example programs and checks it is demo-ready:

1. the session starts and reports a SAS version;
2. each scenario runs with status ``success`` and every output is collected
   (tables with rows, graphs, HTML, a clean log, valid download files);
3. the program on disk is the one that ran (``program_sha256``), unchanged;
4. the run is recorded, and the recording replays offline with identical
   outputs (the demo fallback);
5. WORK is reset between runs: re-running a scenario after another one gives
   the same tables;
6. invalid inputs are rejected before SAS and leave the session usable;
7. a user-uploaded file (xlsx copy of the AML sample) gives the same results
   as the sample;
8. a run on a second session matches the first (no hidden session state).

Run it from ``Python/``:

    SASHINY_LIVE=1 SASHINY_PROFILE=oda SASHINY_ODA_REGION=eu1 \\
    SASHINY_RECORD_TO=../examples/recordings \\
    uv run --extra saspy --extra upload pytest tests/live -v
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

import sashiny
from demo_scenarios import check_result, load_scenarios
from sashiny.recording import key_for

pytestmark = pytest.mark.live

SCENARIOS = load_scenarios()
TODAY = date(2026, 11, 11)
BY_ID = {s.id: s for s in SCENARIOS}


def _tables(result: sashiny.Result) -> dict[str, object]:
    return {k: v["rows"] for k, v in result.outputs.items() if isinstance(v, dict) and "rows" in v}


@pytest.fixture(scope="module")
def runs(live_engine: sashiny.SaspyEngine) -> dict[str, sashiny.Result]:
    """Run every scenario once, in file order, on the recorded session."""
    return {
        s.id: live_engine.run(s.load(), s.values, today=TODAY, uploads=s.uploads) for s in SCENARIOS
    }


def test_session_starts_and_reports_sas_version(live_engine: sashiny.SaspyEngine) -> None:
    version = live_engine._sas_version()
    assert version, "no SAS version: the session did not start"
    assert version[0].isdigit() or version.startswith("V.")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_scenario_is_demo_ready(scenario, runs) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    problems = check_result(runs[scenario.id], contract, scenario)
    assert not problems, f"{scenario.title}:\n  " + "\n  ".join(problems)


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_program_ran_unchanged(scenario, runs) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    on_disk = hashlib.sha256(
        (contract.base_dir / contract.data["program"]).read_bytes()
    ).hexdigest()
    assert runs[scenario.id].metadata["program_sha256"] == on_disk


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.id for s in SCENARIOS])
def test_recording_replays_offline(scenario, runs, record_dir: Path) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    live = runs[scenario.id]
    files = {
        iid: contract.base_dir / contract.data["inputs"][iid]["sample"]
        for iid in scenario.upload_ids
    }
    key = key_for(contract, live.metadata["macros"], files)
    assert (record_dir / f"{key}.json").is_file()
    replay = sashiny.MockEngine(record_dir).run(
        contract, scenario.values, today=TODAY, uploads=scenario.uploads
    )
    assert replay.metadata["recording"] == "replayed"
    assert replay.status == live.status
    assert replay.outputs == live.outputs


def test_work_is_reset_between_runs(live_engine: sashiny.SaspyEngine, runs) -> None:  # type: ignore[no-untyped-def]
    scenario = BY_ID["general"]
    again = live_engine.run(scenario.load(), scenario.values, today=TODAY)
    assert _tables(again) == _tables(runs["general"])
    assert _tables(again) != _tables(runs["general-msrp-40000"])


def test_invalid_input_is_rejected_before_sas(live_engine: sashiny.SaspyEngine) -> None:
    scenario = BY_ID["general"]
    bad = live_engine.run(scenario.load(), {**scenario.values, "min_msrp": -5}, today=TODAY)
    assert bad.status == "error"
    assert bad.metadata["issues"]
    assert "syscc" not in bad.metadata
    good = live_engine.run(scenario.load(), scenario.values, today=TODAY)
    assert good.status == "success"


def test_user_uploaded_xlsx_matches_the_sample(
    scratch_engine: sashiny.SaspyEngine, runs, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    scenario = BY_ID["aml"]
    contract = scenario.load()
    sample = contract.base_dir / contract.data["inputs"]["transactions"]["sample"]
    xlsx = tmp_path / "transactions.xlsx"
    pd.read_csv(sample, dtype=str, keep_default_na=False).to_excel(xlsx, index=False)
    result = scratch_engine.run(
        contract, scenario.values, today=TODAY, uploads={"transactions": xlsx}
    )
    assert check_result(result, contract, scenario) == []
    assert _tables(result) == _tables(runs["aml"])


def test_a_fresh_session_gives_the_same_results(scratch_engine: sashiny.SaspyEngine, runs) -> None:  # type: ignore[no-untyped-def]
    for scenario in (s for s in SCENARIOS if s.primary):
        fresh = scratch_engine.run(
            scenario.load(), scenario.values, today=TODAY, uploads=scenario.uploads
        )
        assert _tables(fresh) == _tables(runs[scenario.id]), scenario.id
