"""Tests for the module rendering helpers (issue #9)."""

from __future__ import annotations

from pathlib import Path

from sashiny import modules
from sashiny.result import Result, TableResult

SPEC = Path(__file__).resolve().parents[2] / "spec"
FIX = SPEC / "fixtures"


def _result(**overrides: object) -> Result:
    r = Result.new("run-1", "success", engine="mock", engine_version="0.0.1")
    for key, value in overrides.items():
        setattr(r, key, value)
    return r


def test_render_status() -> None:
    r = _result()
    assert modules._render_status(r) == "status: success\nrun_id: run-1"


def test_render_status_with_sas_version() -> None:
    r = _result()
    r.metadata["sas_version"] = "9.04.01M8"
    assert "SAS: 9.04.01M8" in modules._render_status(r)


def test_render_log() -> None:
    assert modules._render_log(_result()) == "(no log)"
    assert modules._render_log(_result(log="NOTE: ok\n")) == "NOTE: ok\n"


def test_render_table() -> None:
    assert modules._render_table(_result()) is None
    tbl = TableResult(columns=["a", "b"], rows=[[1, 2]])
    r = _result(outputs={"table": tbl})
    assert modules._render_table(r) == {"columns": ["a", "b"], "rows": [[1, 2]]}


def test_render_plots() -> None:
    assert modules._render_plots(_result()) is None
    r = _result(outputs={"plot": ["<svg/>"]})
    assert modules._render_plots(r) is not None


def test_render_html() -> None:
    assert modules._render_html(_result()) is None
    r = _result(outputs={"html": "<p>hi</p>"})
    assert modules._render_html(r) is not None


def test_render_downloads() -> None:
    assert modules._render_downloads(_result()) is None
    r = _result(outputs={"download": {"csv": b"a,b"}})
    assert modules._render_downloads(r) is not None
