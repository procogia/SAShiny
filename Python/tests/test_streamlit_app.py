"""Tests for the Streamlit front end (spec §6.9) and the streamlit_snowflake target (§6.8.5).

No network and no SAS: widget mapping is checked against the hand-written
fixture, and apps run in Streamlit's AppTest on the internal mock engine.
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

import sashiny
from _repo import repo_root
from engines_helper import save_recording
from sashiny import Result
from sashiny import deploy as d
from sashiny.streamlit_app import _engine, sandboxed_html, to_values, widget_spec
from sashiny.upload import UploadError

FIX = repo_root() / "spec" / "fixtures"
WIDGETS = json.loads((FIX / "streamlit" / "widgets.json").read_text(encoding="utf-8"))
VIYA = {"name": "viya", "method": "http", "url": "https://viya.example.com"}


def _iso(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_iso(v) for v in value]
    return value


@pytest.mark.parametrize("case", WIDGETS["cases"], ids=lambda c: c["name"])
def test_widget_mapping_matches_fixture(case: dict[str, Any]) -> None:
    ws = widget_spec(case["input"], date.fromisoformat(WIDGETS["today"]), case.get("loaded"))
    exp = case["expected"]
    assert ws.widget == exp["widget"]
    assert {k: _iso(v) for k, v in ws.kwargs.items()} == exp["kwargs"]
    assert ws.options == exp.get("options", [])
    assert ws.labels == exp.get("labels", {})


def test_widget_fixture_covers_every_schema_input_variant() -> None:
    schema = json.loads((repo_root() / "spec" / "sashiny.schema.json").read_text("utf-8"))
    types = set(schema["$defs"]["input_common"]["properties"]["type"]["enum"])
    covered = {c["input"]["type"] for c in WIDGETS["cases"]}
    assert covered == types
    widgets = {(c["input"]["type"], c["input"].get("widget")) for c in WIDGETS["cases"]}
    for kind in ("choice", "multichoice"):
        for variant in schema["$defs"][f"input_{kind}"]["properties"]["widget"]["enum"]:
            default = variant == "select"
            assert (kind, variant) in widgets or (default and (kind, None) in widgets)


def _contract(tmp_path: Path, inputs: dict[str, Any], outputs: dict[str, Any]) -> Path:
    (tmp_path / "prog.sas").write_text("proc print data=sashelp.class; run;\n", encoding="utf-8")
    doc = {
        "sashiny": 1,
        "program": "prog.sas",
        "title": "Demo",
        "inputs": inputs,
        "outputs": outputs,
    }
    path = tmp_path / "prog.sashiny.yml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


class _File:
    def __init__(self, name: str, data: bytes) -> None:
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data


def test_to_values_converts_widget_values(tmp_path: Path) -> None:
    path = _contract(
        tmp_path,
        {
            "n": {"type": "numeric", "label": "N"},
            "t": {"type": "text", "label": "T", "optional": True},
            "c": {"type": "choice", "label": "C", "choices": ["a"], "optional": True},
            "m": {"type": "multichoice", "label": "M", "choices": ["a", "b"]},
            "d": {"type": "date", "label": "D"},
            "r": {"type": "daterange", "label": "R"},
            "u": {"type": "dataset", "label": "U", "target": "work.u", "max_size_mb": 1},
        },
        {"log": {"type": "log"}},
    )
    contract = sashiny.load(path)
    values, uploads = to_values(
        contract,
        {
            "n": 3,
            "t": None,
            "c": None,
            "m": ("b",),
            "d": date(2026, 1, 2),
            "r": (date(2026, 1, 1),),
            "u": _File("x.csv", b"a\n1\n"),
        },
    )
    assert values == {"n": 3, "t": "", "c": None, "m": ["b"], "d": "2026-01-02", "r": None}
    assert uploads["u"].name == "x.csv"
    assert uploads["u"].path.read_bytes() == b"a\n1\n"
    with pytest.raises(UploadError, match="limit 1 MB"):
        to_values(contract, {"u": _File("big.csv", b"x" * (2 * 1024 * 1024))})


def test_sandboxed_html_escapes_the_document() -> None:
    wrapped = sandboxed_html('<p onclick="x()">a & b</p><script>alert(1)</script>')
    assert wrapped.startswith('<iframe sandbox="" ')
    assert "<script>" not in wrapped
    assert "&lt;script&gt;" in wrapped
    assert "&quot;x()&quot;" in wrapped


# --------------------------------------------------------------------------- AppTest


def _script(contract: str, recordings: str, *, choices: bool = False) -> None:
    # AppTest runs this function's source as a standalone script, so its
    # imports must be local.
    from engines_helper import MockEngine as Mock  # noqa: PLC0415
    from sashiny.streamlit_app import streamlit_app  # noqa: PLC0415

    extra = {"choices": {"make": ["Acura", "BMW"]}} if choices else {}
    streamlit_app([contract], Mock(recordings, **extra))


def _app_test(contract: Path, recordings: Path, **kwargs: Any) -> Any:
    st_testing = pytest.importorskip("streamlit.testing.v1")
    at = st_testing.AppTest.from_function(
        _script, args=(str(contract), str(recordings)), kwargs=kwargs, default_timeout=30
    )
    return at.run()


def _recorded(tmp_path: Path) -> tuple[Path, Path]:
    path = _contract(
        tmp_path,
        {
            "origin": {
                "type": "choice",
                "label": "Origin",
                "choices": ["Asia", "USA"],
                "default": "USA",
                "widget": "radio",
            },
            "min": {"type": "numeric", "label": "Min", "default": 2, "integer": True},
        },
        {
            "stats": {"type": "table", "label": "Stats", "from": "work.stats"},
            "log": {"type": "log", "label": "Log"},
            "csv": {"type": "download", "label": "CSV", "format": "csv", "from": "work.stats"},
        },
    )
    contract = sashiny.load(path)
    rec = tmp_path / "rec"
    macros = {"ORIGIN": "USA", "MIN": "2"}
    result = Result.new("r1", "success", macros=macros)
    result.log = "NOTE: done"
    result.outputs = {
        "stats": {
            "columns": [{"name": "N", "label": "Count", "type": "numeric"}],
            "rows": [[5]],
            "truncated": False,
            "total_rows": 1,
            "formatted": False,
        },
        "log": [{"text": "NOTE: done", "level": "note"}],
        "csv": {
            "filename": "stats.csv",
            "mime": "text/csv",
            "data": base64.b64encode(b"N\n5\n").decode("ascii"),
        },
    }
    save_recording(rec, contract, result)
    return path, rec


def test_app_renders_widgets_and_runs_in_background(tmp_path: Path) -> None:
    path, rec = _recorded(tmp_path)
    at = _app_test(path, rec)
    assert not at.exception
    assert at.title[0].value == "Demo"
    assert at.radio(key="sashiny-prog-origin").value == "USA"
    assert at.number_input(key="sashiny-prog-min").value == 2
    at.button(key="sashiny-prog-run").click().run()
    for _ in range(20):
        if not at.status:
            break
        at.run()
    assert not at.exception
    assert [s.value for s in at.subheader] == ["Stats", "Log", "CSV"]
    assert at.dataframe[0].value.to_dict("list") == {"Count": [5]}
    assert "status: success" in at.caption[0].value
    assert any("NOTE: done" in c.value for c in at.code)


def test_app_reports_invalid_values_from_the_run(tmp_path: Path) -> None:
    path = _contract(
        tmp_path,
        {"code": {"type": "text", "label": "Code", "pattern": "[A-Z]{3}", "default": "ABC"}},
        {"log": {"type": "log"}},
    )
    at = _app_test(path, tmp_path)
    at.text_input(key="sashiny-prog-code").input("abc; run;")
    at.button(key="sashiny-prog-run").click().run()
    for _ in range(20):
        if not at.status:
            break
        at.run()
    assert not at.exception
    assert any(e.value.startswith("invalid input V") for e in at.error)
    assert "status: error" in at.caption[0].value


def test_app_fills_choices_from(tmp_path: Path) -> None:
    path = _contract(
        tmp_path,
        {
            "make": {
                "type": "choice",
                "label": "Make",
                "choices_from": {"dataset": "sashelp.cars", "value_column": "make"},
            }
        },
        {"log": {"type": "log"}},
    )
    at = _app_test(path, tmp_path, choices=True)
    assert not at.exception
    assert at.selectbox(key="sashiny-prog-make").options == ["Acura", "BMW"]


def test_core_imports_without_streamlit() -> None:
    code = (
        "import sys; sys.modules['streamlit'] = None; import sashiny, sashiny.streamlit_app; "
        "from sashiny import deploy; print(len(deploy.targets()))"
    )
    out = subprocess.run(  # noqa: S603 - fixed interpreter and code
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert int(out.stdout.strip()) >= 1


def test_streamlit_app_rejects_an_object_that_is_not_an_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NotAnEngine:
        def run(self) -> None: ...

    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(TypeError, match=r"engine must come from sashiny\.connect"):
        _engine(None, _NotAnEngine())  # type: ignore[arg-type]


# --------------------------------------------------------------------------- target


def test_streamlit_snowflake_rejects_iom_ssh_and_r(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "app.py").write_text("import shiny\n", encoding="utf-8")
    oda = {"name": "oda", "method": "iom", "oda_region": "us1"}
    with pytest.raises(ValueError, match=r"cannot provide Java 17"):
        d.deploy(app, "streamlit_snowflake", tmp_path / "o1", oda, license_ack=True)
    ssh = {"name": "s", "method": "ssh", "host": "h.example.com", "saspath": "/opt/sas/sas"}
    with pytest.raises(ValueError, match="supports only http"):
        d.deploy(app, "streamlit_snowflake", tmp_path / "o2", ssh, license_ack=True)
    with pytest.raises(ValueError, match="does not support language r"):
        d.deploy(app, "streamlit_snowflake", tmp_path / "o3", VIYA, license_ack=True, language="r")
    with pytest.raises(ValueError, match="title must be"):
        d.deploy(app, "streamlit_snowflake", tmp_path / "o4", VIYA, license_ack=True, title="it's")


def test_streamlit_snowflake_apply_runs_snow(tmp_path: Path) -> None:
    app = tmp_path / "app"
    app.mkdir()
    (app / "app.py").write_text("import shiny\n", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(args, env):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        return 0

    res = d.deploy(
        app,
        "streamlit_snowflake",
        tmp_path / "out",
        VIYA,
        license_ack=True,
        apply=True,
        runner=runner,
    )
    out = str(res.out_dir)
    assert calls == [
        ["snow", "sql", "-f", f"{out}/snowflake/setup.sql"],
        [
            "snow",
            "stage",
            "copy",
            f"{out}/bundle",
            "@SASHINY_DB.APP.SASHINY_STAGE/app",
            "--recursive",
            "--overwrite",
        ],
        ["snow", "sql", "-f", f"{out}/snowflake/streamlit.sql"],
    ]
