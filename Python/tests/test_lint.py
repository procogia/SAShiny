"""Tests for the lint layer (issue #5, §10)."""

from __future__ import annotations

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"


def _codes(issues: list[sashiny.Issue]) -> list[str]:
    return [i.code for i in issues]


def _data(**overrides: object) -> dict:
    data = {
        "sashiny": 1,
        "program": "x.sas",
        "title": "t",
        "inputs": {
            "min_msrp": {"type": "numeric", "label": "Min MSRP"},
        },
        "outputs": {"log": {"type": "log"}},
    }
    data.update(overrides)
    return data


def test_lint_clean_program_returns_empty() -> None:
    data = _data()
    program = "proc print data=sashelp.class; where msrp > &MIN_MSRP; run;"
    assert sashiny.lint(data, program) == []


def test_l001_flags_unassigned_guard() -> None:
    data = _data()
    program = "%let MIN_MSRP = 5;\nproc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L001" in _codes(issues)


def test_l001_ignores_symexist_guard() -> None:
    data = _data()
    program = (
        "%if not %symexist(MIN_MSRP) %then %do;\n"
        "  %let MIN_MSRP = 5;\n"
        "%end;\n"
        "proc print data=sashelp.class; run;"
    )
    issues = sashiny.lint(data, program)
    assert "L001" not in _codes(issues)


def test_l001_flags_call_symput() -> None:
    data = _data()
    program = "data _null_; call symputx('MIN_MSRP', '5'); run;"
    issues = sashiny.lint(data, program)
    assert "L001" in _codes(issues)


def test_l002_flags_unreferenced_macro() -> None:
    data = _data()
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L002" in _codes(issues)


def test_l002_ignores_referenced_macro() -> None:
    data = _data()
    program = "proc print data=sashelp.class; where msrp > &MIN_MSRP; run;"
    issues = sashiny.lint(data, program)
    assert "L002" not in _codes(issues)


def test_l003_flags_uncreated_work_dataset() -> None:
    data = _data(
        outputs={
            "log": {"type": "log"},
            "tbl": {"type": "table", "from": "work.summary"},
        }
    )
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L003" in _codes(issues)


def test_l003_ignores_created_dataset() -> None:
    data = _data(
        outputs={
            "log": {"type": "log"},
            "tbl": {"type": "table", "from": "work.summary"},
        }
    )
    program = "data summary; set sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L003" not in _codes(issues)


def test_l003_ignores_dataset_target() -> None:
    data = _data(
        inputs={
            "min_msrp": {"type": "numeric", "label": "Min MSRP"},
            "ds": {"type": "dataset", "label": "Data", "target": "summary"},
        },
        outputs={
            "log": {"type": "log"},
            "tbl": {"type": "table", "from": "work.summary"},
        },
    )
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L003" not in _codes(issues)


def test_l003_ignores_permanent_library() -> None:
    data = _data(
        outputs={
            "log": {"type": "log"},
            "tbl": {"type": "table", "from": "mylib.summary"},
        }
    )
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L003" not in _codes(issues)


def test_l004_flags_multiple_rtf_pdf() -> None:
    data = _data(
        outputs={
            "log": {"type": "log"},
            "a": {"type": "download", "format": "rtf"},
            "b": {"type": "download", "format": "pdf"},
        }
    )
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L004" in _codes(issues)


def test_l004_ignores_single_rtf() -> None:
    data = _data(
        outputs={
            "log": {"type": "log"},
            "a": {"type": "download", "format": "rtf"},
        }
    )
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L004" not in _codes(issues)


def test_l005_flags_missing_macro() -> None:
    data = _data(run={"entry": "macro", "macro": "report"})
    program = "proc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    assert "L005" in _codes(issues)


def test_l005_ignores_present_macro() -> None:
    data = _data(run={"entry": "macro", "macro": "report"})
    program = "%macro report;\nproc print data=sashelp.class; run;\n%mend report;"
    issues = sashiny.lint(data, program)
    assert "L005" not in _codes(issues)
