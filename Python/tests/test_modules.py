"""Tests for the Shiny module UI (issue #9)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from shiny.types import SilentException

import sashiny
from _repo import repo_root
from sashiny import modules
from sashiny.upload import UploadError

ROOT = repo_root()


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
