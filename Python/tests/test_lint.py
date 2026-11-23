"""Tests for the lint layer (issue #5, §10)."""

from __future__ import annotations

import json

import yaml

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


def test_l001_guard_does_not_exempt_other_macro() -> None:
    # Issue #78: a %symexist guard for one macro must not exempt an assignment
    # to a different injected macro.
    data = _data(
        inputs={
            "min_msrp": {"type": "numeric", "label": "Min MSRP"},
            "ratio": {"type": "numeric", "label": "Ratio"},
        }
    )
    program = (
        "%if not %symexist(MIN_MSRP) %then %do;\n"
        "  %let MIN_MSRP = 5;\n"
        "%end;\n"
        "%let RATIO = 0.5;\n"
        "proc print data=sashelp.class; run;"
    )
    issues = sashiny.lint(data, program)
    codes = _codes(issues)
    assert "L001" in codes
    # Only RATIO is flagged; MIN_MSRP is inside its guard.
    l001 = [i for i in issues if i.code == "L001"]
    assert len(l001) == 1
    assert "RATIO" in l001[0].message


def test_l001_flags_later_assignment_outside_guard() -> None:
    # Issue #78: a later assignment to the same macro outside any guard is L001.
    data = _data()
    program = (
        "%if not %symexist(MIN_MSRP) %then %do;\n"
        "  %let MIN_MSRP = 5;\n"
        "%end;\n"
        "%let MIN_MSRP = 10;\n"
        "proc print data=sashelp.class; run;"
    )
    issues = sashiny.lint(data, program)
    assert "L001" in _codes(issues)


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


def test_l001_path_uses_input_id_when_macro_name_differs() -> None:
    # A macro name that differs from the input id must still map back to the
    # input id (not the lower-cased macro name) in the finding path.
    data = _data(
        inputs={
            "min_msrp": {"type": "numeric", "label": "Min MSRP", "macro": "MSRP"},
        }
    )
    program = "%let MSRP = 5;\nproc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    l001 = [i for i in issues if i.code == "L001"]
    assert len(l001) == 1
    assert l001[0].path == "/inputs/min_msrp"


def test_lint_dedupes_daterange_macro_names() -> None:
    # A daterange sets two macro names that both map to the same input id; the
    # same (code, path) must not be reported twice.
    data = _data(
        inputs={
            "period": {
                "type": "daterange",
                "label": "Period",
                "macro": ["start_dt", "end_dt"],
            },
        }
    )
    program = "%let START_DT = 1;\n%let END_DT = 2;\nproc print data=sashelp.class; run;"
    issues = sashiny.lint(data, program)
    l001 = [i for i in issues if i.code == "L001"]
    assert len(l001) == 1
    assert l001[0].path == "/inputs/period"


def test_lint_fixtures() -> None:
    # spec/fixtures/lint/<name>/: findings must match expected.json exactly (§10).

    dirs = sorted((FIX / "lint").iterdir())
    assert dirs
    for d in dirs:
        data = yaml.safe_load((d / "contract.sashiny.yml").read_text(encoding="utf-8"))
        program = (d / data["program"]).read_text(encoding="utf-8")
        want = json.loads((d / "expected.json").read_text(encoding="utf-8"))["findings"]
        got = [{"code": i.code, "path": i.path} for i in sashiny.lint(data, program)]
        assert got == want, d.name


def _macro_data() -> dict:
    return _data(
        inputs={
            "min_msrp": {"type": "numeric", "label": "Min MSRP"},
            "label": {"type": "text", "label": "Label"},
        },
        run={"entry": "macro", "macro": "report"},
    )


def test_l006_flags_input_without_macro_parameter() -> None:
    # Issue #163: SAS rejects a keyword the entry macro does not define.
    program = "%macro report(Min_Msrp=);\n%put &min_msrp &label;\n%mend report;"
    l006 = [i for i in sashiny.lint(_macro_data(), program) if i.code == "L006"]
    assert [(i.path, i.message) for i in l006] == [
        ("/inputs/label", "%macro report has no parameter LABEL")
    ]


def test_l006_flags_every_input_when_macro_has_no_parameter_list() -> None:
    program = "%macro report;\n%put &min_msrp &label;\n%mend report;"
    paths = [i.path for i in sashiny.lint(_macro_data(), program) if i.code == "L006"]
    assert paths == ["/inputs/min_msrp", "/inputs/label"]


def test_l006_accepts_positional_and_commented_parameters() -> None:
    program = "%macro report(min_msrp, /* text */ LABEL=x);\n%put &min_msrp &label;\n%mend;"
    assert "L006" not in _codes(sashiny.lint(_macro_data(), program))


def test_l006_skips_parmbuff_and_nested_parentheses() -> None:
    for program in (
        "%macro report / parmbuff;\n%put &min_msrp &label;\n%mend;",
        "%macro report(min_msrp=) / PBUFF;\n%put &min_msrp &label;\n%mend;",
        "%macro report(min_msrp=%str(a,b));\n%put &min_msrp &label;\n%mend;",
    ):
        assert "L006" not in _codes(sashiny.lint(_macro_data(), program)), program


def test_l006_needs_entry_macro_and_a_definition() -> None:
    program = "%macro report;\n%put &min_msrp &label;\n%mend;"
    data = _macro_data()
    data.pop("run")
    assert "L006" not in _codes(sashiny.lint(data, program))
    codes = _codes(sashiny.lint(_macro_data(), "%put &min_msrp &label;"))
    assert "L005" in codes
    assert "L006" not in codes
