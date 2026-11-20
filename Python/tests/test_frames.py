"""Data frame accessors (spec §8.7), checked against the shared fixture."""

from __future__ import annotations

import json
import math
import subprocess
import sys
from typing import Any

import pytest

import sashiny
from _repo import repo_root
from sashiny.collect import split_log

FX = json.loads(
    (repo_root() / "spec" / "fixtures" / "collect" / "frames.json").read_text(encoding="utf-8")
)
pd = pytest.importorskip("pandas")


def _result() -> sashiny.Result:
    r = sashiny.Result.new("r1", "error")
    r.outputs = FX["result"]["outputs"]
    r.log = FX["result"]["log"]
    return r


def _py_type(series: Any) -> str:
    if series.dtype == "int64":
        return "integer"
    if series.dtype == "float64":
        return "double"
    return "character"


def _check(df: Any, exp: dict[str, Any]) -> None:
    assert list(df.columns) == [c[0] for c in exp["columns"]]
    assert [_py_type(df[c[0]]) for c in exp["columns"]] == [c[1] for c in exp["columns"]]
    assert len(df) == len(exp["rows"])
    for i, row in enumerate(exp["rows"]):
        for j, want in enumerate(row):
            got = df.iloc[i, j]
            if want is None:
                assert got is None or (isinstance(got, float) and math.isnan(got))
            else:
                assert got == want


@pytest.mark.parametrize("output_id", sorted(FX["expected"]["table"]))
def test_table_matches_fixture(output_id: str) -> None:
    exp = FX["expected"]["table"][output_id]
    df = _result().table(output_id)
    _check(df, exp)
    assert df.attrs["labels"] == exp["labels"]
    assert df.attrs["formats"] == exp["formats"]
    assert df.attrs["total_rows"] == exp["total_rows"]
    assert df.attrs["truncated"] is exp["truncated"]


def test_log_frame_matches_fixture_and_status_rules() -> None:
    df = _result().log_frame()
    _check(df, FX["expected"]["log"])
    lines = split_log(FX["result"]["log"])
    assert (df["type"] == "ERROR").sum() == sum(line.startswith("ERROR") for line in lines)
    assert (df["type"] == "WARNING").sum() == sum(line.startswith("WARNING") for line in lines)


def test_frames_converts_tables_and_logs() -> None:
    out = _result().frames()
    exp = FX["expected"]["outputs"]
    for oid in exp["frames"]:
        assert isinstance(out[oid], pd.DataFrame)
    for oid, rows in exp["log_frames"].items():
        _check(out[oid], {"columns": FX["expected"]["log"]["columns"], "rows": rows})
    for oid in exp["unchanged"]:
        assert out[oid] == FX["result"]["outputs"][oid]


@pytest.mark.parametrize("case", FX["expected"]["errors"], ids=lambda c: c["id"])
def test_errors_name_the_output(case: dict[str, str]) -> None:
    with pytest.raises((KeyError, ValueError)) as info:
        _result().table(case["id"])
    assert case["message"] in str(info.value)


def test_core_imports_without_pandas() -> None:
    code = (
        "import sys; sys.modules['pandas'] = None; import sashiny; r = sashiny.Result.new('r','x');"
        "\ntry:\n    r.log_frame()\nexcept ImportError as e:\n    print(e)"
    )
    out = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert 'pip install "sashiny[frames]"' in out.stdout
