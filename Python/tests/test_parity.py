"""R/Python parity (docs/parity.md). Each test pins a behaviour the R package shares.

The R counterparts are in ``R/tests/testthat/test-parity.R``; the cross-language
cases (values, log scope) are shared fixtures under ``spec/fixtures``.
"""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import sashiny
from _repo import repo_root
from engines_helper import MockEngine, fake_engine
from fakesas import FakeSAS
from sashiny import choices_cache
from sashiny.collect import build_table, split_log
from sashiny.engines import saspy as saspy_engine
from sashiny.lint import lint
from sashiny.pool import PoolExhausted
from sashiny.upload import UploadFile, read_upload
from sashiny.values import render_values

FIX = repo_root() / "spec" / "fixtures"
TODAY = date(2026, 11, 11)
STAMP = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


def _contract(name: str) -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / name / "contract.sashiny.yml")


# --------------------------------------------------------------------------- §2 module id


def test_default_module_id_splits_both_separators_and_strips_all_marks() -> None:
    assert sashiny.default_module_id("C:\\progs\\Cars.sas") == "cars"
    assert sashiny.default_module_id("dir/sub\\Cars.sas") == "cars"
    # U+093F (Devanagari vowel sign I, category Mc) is a combining mark too.
    assert sashiny.default_module_id("a\u093fb.sas") == "ab"


# --------------------------------------------------------------------------- §4 values


def test_render_values_defaults_today() -> None:
    data = _contract("minimal").data
    macros, issues = render_values(data, {})
    assert issues == []
    assert isinstance(macros, dict)


def test_list_inputs_reject_an_empty_string() -> None:
    data = _contract("multichoice").data
    _, issues = render_values(data, {"origins": ["Europe"], "types": "", "arms": ""}, TODAY)
    assert [(i.code, i.path) for i in issues] == [("V002", "types"), ("V002", "arms")]


def test_huge_integer_is_out_of_range_not_a_crash() -> None:
    data = _contract("numeric").data
    _, issues = render_values(data, {"min_msrp": 10**400, "ratio": 0}, TODAY)
    assert [(i.code, i.path) for i in issues] == [("V003", "min_msrp")]


# --------------------------------------------------------------------------- §8 collection


def test_split_log_strips_ascii_blanks_only() -> None:
    assert split_log("a\u00a0\nb \t\nc\u3000") == ["a\u00a0", "b", "c\u3000"]


def test_table_label_and_format_are_trimmed_and_missing_is_empty() -> None:
    meta = [
        {"name": "a", "type": "numeric", "label": "  Age  ", "format": float("nan")},
        {"name": "b", "type": "character", "label": None, "format": " $8. "},
    ]
    value = build_table(meta, [[1, "x"]], total_rows=1, max_rows=10, formatted=False)
    assert [(c["label"], c["format"]) for c in value["columns"]] == [("Age", ""), ("", "$8.")]


def test_lint_word_boundaries_are_ascii() -> None:
    data = {
        "program": "p.sas",
        "inputs": {"n": {"type": "numeric", "label": "N"}},
        "outputs": {"log": {"type": "log"}},
    }
    # `&Né`: é is not an ASCII word character, so `&N` is referenced (no L002), as in R.
    assert [i.code for i in lint(data, "%put &N\u00e9;")] == []


# --------------------------------------------------------------------------- §8.4 metadata


def test_mock_metadata_uses_package_version_and_utc_stamps() -> None:
    result = MockEngine().run(_contract("minimal"), {}, today=TODAY)
    meta = result.metadata
    assert meta["engine_version"] == sashiny.__version__
    assert STAMP.match(meta["started_at"]), meta["started_at"]
    assert STAMP.match(meta["ended_at"]), meta["ended_at"]


def test_saspy_engine_version_is_the_package_version() -> None:
    engine = fake_engine(FakeSAS)
    assert engine.version == sashiny.__version__
    result = engine.run(_contract("minimal"), {}, today=TODAY)
    assert result.metadata["engine_version"] == sashiny.__version__
    assert STAMP.match(result.metadata["ended_at"])


def test_engine_error_is_the_bare_message() -> None:
    def broken() -> Any:
        raise RuntimeError("Java was not found")

    result = fake_engine(broken).run(_contract("minimal"), {}, today=TODAY)
    assert result.metadata["engine_error"] == "Java was not found"


# --------------------------------------------------------------------------- §6.4, §6.5 engines


def _choices_contract(tmp_path: Path) -> sashiny.Contract:
    (tmp_path / "program.sas").write_text("data _null_; run;\n", encoding="utf-8")
    (tmp_path / "c.sashiny.yml").write_text(
        "sashiny: 1\nprogram: program.sas\ntitle: Choices\ninputs:\n  make:\n    type: choice\n"
        "    label: Make\n    choices_from: {dataset: sashelp.cars, value_column: make}\n"
        "outputs:\n  log:\n    type: log\n",
        encoding="utf-8",
    )
    return sashiny.load(tmp_path / "c.sashiny.yml")


class _ErrorEngine(MockEngine):
    def __init__(self) -> None:
        super().__init__(choices={"make": ["Acura"]})

    def run(self, contract, values, *, today=None, uploads=None, run_id=None):  # type: ignore[no-untyped-def]
        return sashiny.Result.new(run_id or "r", "error")


def test_pool_clears_choices_cache_when_it_discards_a_session(tmp_path: Path) -> None:
    contract = _choices_contract(tmp_path)
    pool = sashiny.Pool(_ErrorEngine, max_size=1)
    choices_cache.load(pool, contract)
    assert choices_cache.cached(pool, contract) is not None
    assert pool.run(contract, {"make": "Acura"}, today=TODAY).status == "error"
    assert choices_cache.cached(pool, contract) is None  # #152
    pool.close()


def test_saspy_close_clears_the_choices_cache(tmp_path: Path) -> None:
    contract = _choices_contract(tmp_path)
    engine = fake_engine(FakeSAS)
    choices_cache.store(engine, contract, {"make": [{"value": "A", "label": "A"}]})
    engine.close()
    assert choices_cache.cached(engine, contract) is None


def test_closed_pool_reports_pool_closed_and_errors_are_sashiny_errors() -> None:
    pool = sashiny.Pool(MockEngine(), max_size=1)
    pool.close()
    result = pool.run(_contract("minimal"), {}, today=TODAY)
    assert result.metadata["engine_error"] == "pool closed"
    assert issubclass(PoolExhausted, sashiny.EngineError)
    with pytest.raises(sashiny.SashinyError, match="pool closed"):
        pool.choices(_contract("minimal"))


def test_second_run_on_a_busy_engine_waits_then_reports_busy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(saspy_engine, "BUSY_WAIT_SECONDS", 0.2)
    gate = threading.Event()

    class SlowSAS(FakeSAS):
        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            if "SASHINY-BEGIN run=" in code:
                gate.wait(5)
            return super().submit(code, results)

    engine = fake_engine(SlowSAS)
    contract = _contract("minimal")
    first: dict[str, sashiny.Result] = {}
    worker = threading.Thread(target=lambda: first.setdefault("r", engine.run(contract, {})))
    worker.start()
    time.sleep(0.2)
    second = engine.run(contract, {})
    gate.set()
    worker.join(10)
    assert second.metadata["engine_error"] == "engine busy: another run is in progress"
    assert first["r"].status == "success"  # the first run was not cancelled


# --------------------------------------------------------------------------- §6.6, §6.8 connect


def test_connect_rejects_connection_arguments_next_to_a_backend() -> None:
    with pytest.raises(sashiny.EngineError, match="backend constructor"):
        sashiny.connect(sashiny.oda("us1", java="java"), region="us2")


def test_connect_from_env_treats_an_empty_region_as_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SASHINY_PROFILE", "oda")
    monkeypatch.setenv("SASHINY_ODA_REGION", "")
    engine = sashiny.connect_from_env(license_ack=True)
    assert engine.cfg["iomhost"] == ["odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"]


def test_profile_errors_are_deploy_errors() -> None:
    with pytest.raises(sashiny.DeployError, match=r"^profile p: "):
        sashiny.parse_profile({"method": "nope"}, name="p")


# --------------------------------------------------------------------------- §8.5 charts


def _chart_value() -> dict[str, Any]:
    return {
        "columns": [
            {"name": "g", "type": "character", "label": "", "format": ""},
            {"name": "x", "type": "numeric", "label": "", "format": ""},
            {"name": "y", "type": "numeric", "label": "", "format": ""},
        ],
        "rows": [["a", 1, 2], ["b", 2, 3]],
        "total_rows": 2,
        "truncated": False,
        "formatted": False,
    }


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        ({"kind": "scatter", "x": "x", "y": "y", "fill": "g"}, "cannot map fill for kind scatter"),
        ({"kind": "bar", "x": "g", "y": "y", "color": "g"}, "cannot map color for kind bar"),
        ({"kind": "histogram", "x": "x", "color": "g"}, "cannot map color for kind histogram"),
        ({"kind": "box", "x": "g", "y": "y", "color": "x"}, "cannot map color for kind box"),
    ],
)
def test_matplotlib_refuses_mappings_it_cannot_draw(spec: dict[str, Any], message: str) -> None:
    pytest.importorskip("matplotlib")
    with pytest.raises(sashiny.ValuesError, match=f"chart backend matplotlib {message}"):
        sashiny.render_chart(_chart_value(), spec, backend="matplotlib")


def test_matplotlib_honours_axis_labels() -> None:
    pytest.importorskip("matplotlib")
    spec = {"kind": "scatter", "x": "x", "y": "y", "xlab": "Height", "ylab": "Weight"}
    fig = sashiny.render_chart(_chart_value(), spec, backend="matplotlib")
    ax = fig.axes[0]
    assert (ax.get_xlabel(), ax.get_ylabel()) == ("Height", "Weight")


def test_plotly_refuses_color_and_fill_together() -> None:
    pytest.importorskip("plotly")
    spec = {"kind": "bar", "x": "g", "y": "y", "color": "g", "fill": "g"}
    with pytest.raises(sashiny.ValuesError, match="cannot map both color and fill"):
        sashiny.render_chart(_chart_value(), spec, backend="plotly")


def test_render_chart_spec_defaults_to_none() -> None:
    with pytest.raises(sashiny.ValuesError, match="no spec and no render callback"):
        sashiny.render_chart(_chart_value())


# --------------------------------------------------------------------------- §7 uploads


def test_declared_character_cells_use_the_section_7_1_text() -> None:
    folder = FIX / "uploads" / "character_cells"
    case = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    spec = {
        "type": "dataset",
        "label": "Cells",
        "target": "work.cells",
        "accept": ["xlsx"],
        "columns": [{"name": c, "type": "character"} for c in case["columns"]],
    }
    path = folder / case["file"]
    df, _ = read_upload(UploadFile(path=path, name=case["file"]), spec)
    assert {c: list(df[c]) for c in case["columns"]} == case["expected"]
