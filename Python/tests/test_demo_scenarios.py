"""Offline checks for the demo scenarios (no SAS needed).

- The scenario file matches the contracts: values are valid, and primary
  scenarios equal what the untouched UI sends (so recordings match).
- The result checker itself catches every kind of problem.
- Committed recordings replay for every scenario. Missing recordings skip,
  or fail when ``SASHINY_REQUIRE_RECORDINGS=1`` (use before the demo).
"""

from __future__ import annotations

import base64
import os
from datetime import date

import pytest

import sashiny
from demo_scenarios import MAGIC, RECORDINGS, check_result, default_problems, load_scenarios

SCENARIOS = load_scenarios()
IDS = [s.id for s in SCENARIOS]
TODAY = date(2026, 11, 11)


def test_scenario_ids_are_unique_and_each_track_has_a_primary() -> None:
    assert len(IDS) == len(set(IDS))
    primaries = {s.contract_path for s in SCENARIOS if s.primary}
    assert primaries == {s.contract_path for s in SCENARIOS}


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_scenario_values_are_valid(scenario) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    assert not contract.issues
    macros, issues = sashiny.render_values(
        contract.data, scenario.values, TODAY, uploads=dict.fromkeys(scenario.upload_ids, True)
    )
    assert issues == []
    assert macros
    for oid in list(scenario.expect.get("tables") or {}) + list(scenario.expect.get("plots") or {}):
        assert oid in contract.data["outputs"], f"{scenario.id}: unknown output {oid}"


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.primary], ids=lambda s: s.id)
def test_primary_scenarios_equal_the_ui_defaults(scenario) -> None:  # type: ignore[no-untyped-def]
    assert default_problems(scenario, scenario.load()) == []


# --------------------------------------------------------------------------- checker self-test


def _good_result(contract: sashiny.Contract) -> sashiny.Result:
    result = sashiny.Result.new("r", "success")
    for oid, spec in contract.data["outputs"].items():
        kind = spec["type"]
        if kind == "table":
            result.outputs[oid] = {
                "columns": [{"name": "a", "type": "character", "label": "", "format": ""}],
                "rows": [["x"]],
                "total_rows": 1,
                "truncated": False,
                "formatted": True,
            }
        elif kind == "plot":
            result.outputs[oid] = [{"mime": "image/png", "data": "QQ=="}]
        elif kind == "html":
            result.outputs[oid] = "<html><body>ok</body></html>"
        elif kind == "log":
            result.outputs[oid] = [{"level": "note", "text": "NOTE: ok"}]
        else:
            fmt = spec["format"]
            data = b"a,b\n1,2\n" if fmt == "csv" else MAGIC[fmt] + b"rest"
            result.outputs[oid] = {
                "filename": f"{spec.get('filename', oid)}.{fmt}",
                "mime": "x",
                "data": base64.b64encode(data).decode(),
            }
    return result


@pytest.mark.parametrize("scenario", [s for s in SCENARIOS if s.primary], ids=lambda s: s.id)
def test_checker_accepts_a_complete_result(scenario) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    assert check_result(_good_result(contract), contract, scenario) == []


def test_checker_reports_every_problem() -> None:
    scenario = next(s for s in SCENARIOS if s.id == "general")
    contract = scenario.load()
    result = _good_result(contract)
    result.status = "warning"
    result.metadata["collect_errors"] = ["report_pdf: download failed"]
    result.outputs["stats"]["rows"] = []
    result.outputs["price_vs_mpg"] = []
    result.outputs["report"] = "plain text"
    result.outputs["log"] = [{"level": "error", "text": "ERROR: boom"}]
    result.outputs["report_pdf"] = {
        "filename": "cars_report.pdf",
        "mime": "application/pdf",
        "data": base64.b64encode(b"not a pdf").decode(),
    }
    result.outputs["stats_csv"] = {"error": "dataset WORK.CARS_STATS not found"}
    del result.outputs["price_by_type"]
    problems = "\n".join(check_result(result, contract, scenario))
    for expected in [
        "status 'warning'",
        "collect error: report_pdf",
        "stats: 0 rows",
        "price_vs_mpg: 0 graphs",
        "price_by_type: missing",
        "report: not an HTML document",
        "SAS log error: ERROR: boom",
        "report_pdf: not a valid .pdf",
        "stats_csv: dataset WORK.CARS_STATS not found",
    ]:
        assert expected in problems


def test_default_problems_detects_drift() -> None:
    scenario = next(s for s in SCENARIOS if s.id == "general-msrp-40000")
    assert default_problems(scenario, scenario.load()) == [
        "min_msrp: scenario value 40000 != contract default 20000"
    ]


# --------------------------------------------------------------------------- committed recordings


@pytest.mark.parametrize("scenario", SCENARIOS, ids=IDS)
def test_committed_recording_replays(scenario) -> None:  # type: ignore[no-untyped-def]
    contract = scenario.load()
    result = sashiny.MockEngine(RECORDINGS).run(
        contract, scenario.values, today=TODAY, uploads=scenario.uploads
    )
    if result.metadata.get("recording") == "missing":
        message = f"no recording for {scenario.id} in examples/recordings"
        if os.environ.get("SASHINY_REQUIRE_RECORDINGS") == "1":
            pytest.fail(message)
        pytest.skip(message)
    assert check_result(result, contract, scenario) == []
