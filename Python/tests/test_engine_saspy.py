"""Tests for the saspy engine interface (issue #6).

These tests exercise the parts that do not require a live SAS session: profile
loading and log classification/status. Live verification is deferred to #11.
"""

from __future__ import annotations

from pathlib import Path

from sashiny.engines.saspy import classify_log, load_profiles, run_status


def test_load_profiles_defaults_to_offline(tmp_path: Path) -> None:
    profiles = load_profiles(tmp_path / "missing.yml")
    assert profiles["default"] == "offline"
    assert profiles["profiles"] == {}


def test_load_profiles_reads_file(tmp_path: Path) -> None:
    path = tmp_path / "connections.yml"
    path.write_text(
        "default: oda\nprofiles:\n  oda:\n    method: iom\n    oda_region: us1\n",
        encoding="utf-8",
    )
    profiles = load_profiles(path)
    assert profiles["default"] == "oda"
    assert profiles["profiles"]["oda"]["method"] == "iom"


def test_classify_log() -> None:
    log = "NOTE: ok\nERROR: bad\nWARNING: careful\n"
    counts = classify_log(log)
    assert counts == {"error": 1, "warning": 1}


def test_run_status_success() -> None:
    log = "NOTE: SASHINY-END run=fixture syscc=0\n"
    assert run_status(log) == ("success", 0)


def test_run_status_error_missing_sentinel() -> None:
    assert run_status("NOTE: nothing here") == ("error", None)


def test_run_status_error_syscc() -> None:
    log = "NOTE: SASHINY-END run=fixture syscc=3000\n"
    assert run_status(log) == ("error", 3000)
