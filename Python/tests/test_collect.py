"""Tests for result collection helpers against the shared fixtures (spec §8)."""

from __future__ import annotations

import base64
import csv
import io
import json
from pathlib import Path

import pytest

from sashiny import collect

FIX = Path(__file__).resolve().parents[2] / "spec" / "fixtures" / "collect"


def _cases(name: str) -> dict:
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", _cases("log_scope.json")["cases"], ids=lambda c: c["name"])
def test_scope_log_fixture(case: dict) -> None:
    assert collect.scope_log(case["log"], case["scope"]) == case["expected"]


@pytest.mark.parametrize("case", _cases("plots.json")["cases"], ids=lambda c: c["name"])
def test_extract_plots_fixture(case: dict) -> None:
    html = _cases("plots.json")["html"]
    if "expected_error" in case:
        with pytest.raises(ValueError, match="graph"):
            collect.extract_plots(html, case["select"])
    else:
        assert collect.extract_plots(html, case["select"]) == case["expected"]


def test_recording_key_fixture() -> None:
    case = _cases("recording_key.json")
    macros = [tuple(m) for m in case["macros"]]
    uploads = [tuple(u) for u in case["uploads"]]
    assert collect.recording_key_text(case["contract_sha256"], macros, uploads) == case["key_text"]
    assert collect.recording_key(case["contract_sha256"], macros, uploads) == case["key"]


def test_split_log_handles_all_line_breaks() -> None:
    assert collect.split_log("a\r\nb\rc\nd  \n") == ["a", "b", "c", "d"]
    assert collect.split_log("") == []


def test_table_meta_code_uses_upper_case_names() -> None:
    code = collect.table_meta_code("WORK", "STATS")
    assert 'where libname = "WORK" and memname = "STATS"' in code
    assert code.endswith("quit;\n")


def test_formatted_table_code() -> None:
    code = collect.formatted_table_code("WORK", "STATS", ["a", "b"], 5)
    assert "set WORK.STATS(obs=5 keep=a b);" in code
    assert "_sx_c2 = strip(vvalue(b));" in code
    assert "length _sx_c1-_sx_c2 $512;" in code


def test_choices_code_with_and_without_label() -> None:
    plain = collect.choices_code({"dataset": "sashelp.cars", "value_column": "make"})
    assert "select distinct make\n" in plain
    assert "proc sql outobs=1000 noprint;" in plain
    labelled = collect.choices_code(
        {"dataset": "sashelp.cars", "value_column": "make", "label_column": "lbl", "max_choices": 5}
    )
    assert "select distinct make, lbl\n" in labelled
    assert "outobs=5" in labelled


def test_build_table_raw_and_formatted() -> None:
    meta = [
        {"name": "x", "type": "numeric", "label": "X", "format": ""},
        {"name": "s", "type": "character", "label": None, "format": None},
    ]
    raw = collect.build_table(
        meta, [[1.0, "a  "], [float("nan"), None]], total_rows=3, max_rows=2, formatted=False
    )
    assert raw["rows"] == [[1, "a"], [None, None]]
    assert raw["truncated"] is True
    assert raw["columns"][1] == {"name": "s", "type": "character", "label": "", "format": ""}
    fmt = collect.build_table(meta, [[" 1 ", None]], total_rows=None, max_rows=2, formatted=True)
    assert fmt["rows"] == [["1", ""]]
    assert fmt["truncated"] is False


def test_select_columns() -> None:
    meta = [{"name": "A"}, {"name": "b"}]
    assert collect.select_columns(meta, None) == meta
    assert collect.select_columns(meta, ["B", "a"]) == [{"name": "b"}, {"name": "A"}]
    with pytest.raises(ValueError, match="not found"):
        collect.select_columns(meta, ["zz"])


def test_join_remote() -> None:
    assert collect.join_remote("/sas/work/", "a.rtf") == "/sas/work/a.rtf"
    assert collect.join_remote("C:\\SAS\\Work", "a.rtf") == "C:\\SAS\\Work\\a.rtf"


def _table() -> dict:
    meta = [
        {"name": "id", "type": "numeric", "label": "Subject", "format": ""},
        {"name": "txt", "type": "character", "label": "", "format": ""},
    ]
    return collect.build_table(
        meta, [[1, 'a,"b"'], [None, "c"]], total_rows=2, max_rows=10, formatted=False
    )


def test_csv_bytes_quotes_and_missing() -> None:
    data = collect.csv_bytes(_table()).decode("utf-8")
    assert data == 'id,txt\n1,"a,""b"""\n,c\n'
    assert list(csv.reader(io.StringIO(data)))[1] == ["1", 'a,"b"']


def test_xlsx_bytes_round_trip() -> None:
    pd = pytest.importorskip("pandas")
    pytest.importorskip("openpyxl")
    df = pd.read_excel(io.BytesIO(collect.xlsx_bytes(_table(), "STATS")), sheet_name="STATS")
    assert list(df.columns) == ["id", "txt"]


def test_xpt_bytes_version_choice() -> None:
    pytest.importorskip("pyreadstat")
    short = collect.xpt_bytes(_table(), "STATS")
    assert short.startswith(b"HEADER RECORD*******LIBRARY HEADER RECORD")
    long_member = collect.xpt_bytes(_table(), "A_VERY_LONG_NAME")
    assert b"LIBV8" in long_member


def test_download_value() -> None:
    value = collect.download_value("out", "csv", b"a\n")
    assert value == {
        "filename": "out.csv",
        "mime": "text/csv",
        "data": base64.b64encode(b"a\n").decode(),
    }
