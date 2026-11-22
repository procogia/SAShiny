"""Tests for the Shiny module UI (issue #9)."""

from __future__ import annotations

import asyncio
import datetime as dt
import tempfile
from pathlib import Path

import pytest
from shiny.types import SilentException

import sashiny
from _repo import repo_root
from engines_helper import MockEngine
from sashiny import modules
from sashiny.upload import UploadError

ROOT = repo_root()
FIX = ROOT / "spec" / "fixtures"


def test_program_ui_has_one_card_per_output() -> None:
    contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    html = str(modules.program_ui("cars", contract))
    for oid, spec in contract.data["outputs"].items():
        # Downloads render a conditional button placeholder (issue #51); other
        # outputs render a static output_ui.
        expected = f"cars-dl_btn_{oid}" if spec["type"] == "download" else f"cars-out_{oid}"
        assert expected in html, oid
    assert "Summarise" in html
    assert "cars-status" in html


def test_program_ui_run_button_is_a_task_button() -> None:
    # A task button shows a busy state and is disabled until the run finishes.
    contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    html = str(modules.program_ui("cars", contract))
    assert "bslib-task-button" in html
    assert 'id="cars-run"' in html
    assert "Summarise" in html
    assert "Running..." in html


def test_program_ui_top_layout_and_override() -> None:
    contract = sashiny.load(ROOT / "examples" / "general" / "cars_explorer.sashiny.yml")
    contract.data["ui"]["layout"] = "top"
    assert "bslib-sidebar-layout" not in str(modules.program_ui("x", contract))
    custom = modules.program_ui("y", contract, ui_override=lambda c: "custom")
    assert "custom" in str(custom)


def test_program_server_is_callable() -> None:
    assert callable(modules.program_server)


def test_download_handler_404s_without_result() -> None:
    # Issue #51: downloading before a run (or after a failed run) must raise a
    # SilentException (HTTP 404), not return an empty 200 or a 500 traceback.
    captured: dict[str, object] = {}

    class _Outputs:
        def __call__(self, id: str):
            def deco(fn):
                captured[id] = fn
                return fn

            return deco

    modules._register_download(_Outputs(), "report", {"type": "download"}, lambda: None)
    # The renderer's `filename` closure calls `_value()`, which calls `req()`
    # and raises SilentException when there is no result (issue #51).
    renderer = captured["dl_report"]
    with pytest.raises(SilentException):
        renderer.filename()


def test_download_button_gated_until_result() -> None:
    # Issue #51: the download button is rendered only once a result with that
    # output exists; before that a disabled placeholder is shown.
    captured: dict[str, object] = {}

    class _Outputs:
        def __call__(self, id: str):
            def deco(fn):
                captured[id] = fn
                return fn

            return deco

    modules._register_download(_Outputs(), "report", {"type": "download"}, lambda: None)
    button = captured["dl_btn_report"]
    # The button renderer is a `render.ui` renderer; its `fn` is async, so await it.
    html = str(asyncio.run(button.fn()))
    assert "disabled" in html
    assert "Download" in html
    # The placeholder must not reuse the output's id (Shiny reports a shared
    # input/output id).
    assert "id=" not in html


def test_upload_size_checked_when_received() -> None:
    # Issue #54: an upload over max_size_mb must be refused when received, not
    # only later in read_upload.
    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"x\n" + b"1\n" * 1000)
        path = f.name
    try:
        upload = modules.UploadFile(path=Path(path), name="big.csv")
        with pytest.raises(UploadError, match="limit"):
            modules._check_upload_size(upload, {"max_size_mb": 0.0001})
    finally:
        Path(path).unlink(missing_ok=True)


def test_upload_size_uses_declared_size() -> None:
    # Issue #54: the client-declared size from uploadInit is used, so an
    # oversized upload is refused even before the file is stat'ed.
    upload = modules.UploadFile(path=Path("does-not-exist.csv"), name="big.csv")
    with pytest.raises(UploadError, match="limit"):
        modules._check_upload_size(upload, {"max_size_mb": 0.0001}, declared_size=200_000)


def test_oversized_upload_becomes_v014_result() -> None:
    # Issue #101: an upload refused on receipt is shown as V014 in the status
    # card (like R), not raised out of the Run effect.
    contract = sashiny.load(FIX / "contracts" / "valid" / "dataset" / "contract.sashiny.yml")
    info = {"name": "big.csv", "size": 51 * 1024 * 1024, "datapath": "missing.csv"}

    def read(iid: str) -> object:
        return [info] if iid == "adsl" else None

    with pytest.raises(UploadError) as caught:
        modules.shiny_values(contract, read)
    result = modules._upload_error_result(caught.value)
    assert result.status == "error"
    text = modules._status_text(result)
    assert "status: error" in text
    assert "invalid input V014" in text
    assert "big.csv is 51.0 MB (limit 20 MB)" in text


# External values (spec §6.10) ---------------------------------------------


def _numeric() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")


def test_merge_values_precedence_and_forms() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "dates" / "contract.sashiny.yml")
    ids = list(contract.data["inputs"])
    merged = modules.merge_values(
        contract, {ids[0]: "2024-01-01", "keep": 1}, {ids[0]: dt.date(2024, 3, 4)}
    )
    assert merged == {ids[0]: "2024-03-04", "keep": 1}
    assert modules.merge_values(contract, {ids[0]: "x"}, {ids[0]: None}) == {}
    assert modules.merge_values(contract, {"a": 1}, None) == {"a": 1}
    with pytest.raises(sashiny.errors.ValuesError):
        modules.merge_values(contract, {}, [1])  # type: ignore[arg-type]


def test_merge_values_leaves_dataset_ids_to_merge_uploads() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "dataset" / "contract.sashiny.yml")
    dataset_ids = [i for i, s in contract.data["inputs"].items() if s["type"] == "dataset"]
    assert modules.merge_values(contract, {}, {dataset_ids[0]: "not a frame"}) == {}
    # The value goes to the uploads (spec 6.10) and is refused with V014 at run time.
    merged = modules.merge_uploads(contract, {}, {dataset_ids[0]: "not a frame"})
    assert isinstance(merged[dataset_ids[0]], modules.FrameUpload)


def test_snapshot_merges_external_values_and_validates() -> None:
    contract = _numeric()
    ui_values = {"min_msrp": 20000, "ratio": 0.25, "big": 1}
    snap = modules._snapshot_inputs(contract, ui_values.get, {"min_msrp": 40000})
    assert not isinstance(snap, sashiny.Result)
    result = MockEngine().run(contract, snap[0], uploads=snap[1])
    assert result.status == "success"
    assert result.metadata["macros"]["MIN_MSRP"] == "40000"
    assert result.metadata["macros"]["RATIO_VALUE"] == "0.25"

    snap = modules._snapshot_inputs(contract, ui_values.get, {"min_msrp": 999999, "nope": 1})
    assert not isinstance(snap, sashiny.Result)
    bad = MockEngine().run(contract, snap[0], uploads=snap[1])
    assert bad.status == "error"
    assert {i["code"] for i in bad.metadata["issues"]} == {"V003", "V011"}


def test_hide_inputs_tag_lists_only_supplied_ids() -> None:
    html = str(modules._hide_inputs_tag(["min_msrp"], lambda x: f"mod-{x}"))
    assert "#mod-in__min_msrp" in html
    assert "ratio" not in html
    assert modules._hide_inputs_tag([], lambda x: x) is None


def test_program_ui_wraps_inputs_for_hiding() -> None:
    html = str(modules.program_ui("mod", _numeric()))
    assert 'id="mod-in__min_msrp"' in html
    assert 'id="mod-hide__inputs"' in html
