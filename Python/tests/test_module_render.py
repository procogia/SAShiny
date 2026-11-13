"""Tests for the module rendering helpers and value conversion (issue #9)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import sashiny
from _repo import repo_root
from sashiny import modules
from sashiny.result import Result
from sashiny.upload import UploadFile

FIX = repo_root() / "spec" / "fixtures"


def _result() -> Result:
    return Result.new("run-1", "success", engine="mock", engine_version="0.1.0")


def test_status_text() -> None:
    r = _result()
    assert modules._status_text(r) == "status: success\nrun_id: run-1"
    r.metadata.update(
        sas_version="9.04.01M8",
        recording="missing",
        issues=[{"code": "V002", "input": "n"}],
        engine_error="boom",
        collect_errors=["t: gone"],
    )
    text = modules._status_text(r)
    for part in ["SAS: 9.04.01M8", "no recording", "V002 n", "engine error: boom", "t: gone"]:
        assert part in text
    r.metadata["recording"] = "replayed"
    r.metadata["recorded_at"] = "2026-11-01"
    assert "replayed recording from 2026-11-01" in modules._status_text(r)


def test_table_tag() -> None:
    value = {
        "columns": [
            {"name": "n", "type": "numeric", "label": "Count", "format": ""},
            {"name": "s", "type": "character", "label": "", "format": ""},
        ],
        "rows": [[1, "<b>"], [None, "x"]],
        "total_rows": 9,
        "truncated": True,
        "formatted": False,
    }
    html = str(modules.table_tag(value))
    assert "Count" in html
    assert "&lt;b&gt;" in html  # cell text is escaped
    assert "Showing 2 of 9 rows." in html
    assert 'class="text-end"' in html


def test_plot_html_log_tags() -> None:
    assert "No graphs" in str(modules.plot_tag([]))
    img = str(modules.plot_tag([{"mime": "image/png", "data": "QUJD"}]))
    assert 'src="data:image/png;base64,QUJD"' in img
    frame = str(modules.html_tag("<p>hi</p>"))
    assert 'sandbox=""' in frame
    assert "srcdoc" in frame
    assert "No HTML" in str(modules.html_tag(""))
    log = str(modules.log_tag([{"level": "error", "text": "ERROR: x"}]))
    assert "#b42318" in log
    assert "ERROR: x" in log


def test_error_tag() -> None:
    assert modules._error_tag([1]) is None
    assert "gone" in str(modules._error_tag({"error": "gone"}))


def test_input_ui_each_kind_uses_defaults() -> None:
    today = date(2026, 11, 11)
    cases = [
        ({"type": "numeric", "label": "N", "default": 7, "min": 0}, 'value="7"'),
        ({"type": "text", "label": "T", "default": "abc"}, 'value="abc"'),
        ({"type": "choice", "label": "C", "choices": ["a", "b"], "default": "b"}, "selected"),
        ({"type": "choice", "label": "C", "choices": ["a"], "widget": "radio"}, 'type="radio"'),
        (
            {"type": "multichoice", "label": "M", "choices": ["a", "b"], "widget": "checkbox"},
            "checkbox",
        ),
        (
            {"type": "multichoice", "label": "M", "choices": [{"value": "a", "label": "A"}]},
            "multiple",
        ),
        ({"type": "date", "label": "D", "default": "today"}, "2026-11-11"),
        ({"type": "daterange", "label": "R", "default": ["2026-01-01", "today"]}, "2026-01-01"),
        (
            {"type": "dataset", "label": "F", "target": "work.x", "sample": "x.csv"},
            "Use the sample",
        ),
    ]
    for spec, expected in cases:
        assert expected in str(modules._input_ui("i", spec, today)), spec


def test_ordered_inputs() -> None:
    contract = sashiny.load(repo_root() / "examples" / "general" / "cars_explorer.sashiny.yml")
    assert [i for i, _ in modules._ordered_inputs(contract)] == ["origins", "types", "min_msrp"]


def test_shiny_values_conversion(tmp_path: Path) -> None:
    contract = sashiny.Contract(
        data={
            "sashiny": 1,
            "program": "p.sas",
            "inputs": {
                "n": {"type": "numeric"},
                "c": {"type": "choice", "choices": ["a"]},
                "m": {"type": "multichoice", "choices": ["a", "b"]},
                "d": {"type": "date"},
                "r": {"type": "daterange"},
                "r2": {"type": "daterange"},
                "f": {"type": "dataset", "target": "work.f"},
                "s": {"type": "dataset", "target": "work.s", "sample": "s.csv"},
                "t": {"type": "text"},
            },
            "outputs": {},
        },
        base_dir=tmp_path,
    )
    shiny = {
        "n": 3,
        "c": "",
        "m": ("a", "b"),
        "d": date(2026, 1, 2),
        "r": (date(2026, 1, 1), date(2026, 2, 1)),
        "r2": (None, None),
        "f": [{"name": "real.csv", "datapath": str(tmp_path / "0.csv")}],
        "s__sample": True,
        "t": " hi ",
    }
    values, uploads = modules.shiny_values(contract, shiny.get)
    assert values == {
        "n": 3,
        "c": None,
        "m": ["a", "b"],
        "d": "2026-01-02",
        "r": ["2026-01-01", "2026-02-01"],
        "r2": None,
        "t": " hi ",
    }
    assert uploads == {"f": UploadFile(path=tmp_path / "0.csv", name="real.csv"), "s": True}
