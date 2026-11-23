"""Tests for the internal offline mock engine (issue #5; a test fixture, spec §6.6)."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import sashiny
from _repo import repo_root
from engines_helper import MockEngine
from sashiny.engines import _mock
from sashiny.recording import save_recording
from sashiny.result import utc_timestamp

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)
STAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def test_mock_engine_empty_success() -> None:
    engine = MockEngine()
    contract = _minimal_contract()
    result = engine.run(contract, {}, today=TODAY)
    assert result.status == "success"
    assert result.run_id
    assert result.metadata["engine"] == "mock"


def test_mock_engine_invalid_values() -> None:
    engine = MockEngine()
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = engine.run(contract, {"min_msrp": "not-a-number"}, today=TODAY)
    assert result.status == "error"


def test_mock_engine_replay(tmp_path: Path) -> None:
    engine = MockEngine(recordings_dir=tmp_path)
    contract = _minimal_contract()
    # Save a recording for the empty-macros key.
    macros: dict[str, str] = {}
    key = _mock._recording_key(contract, macros)
    recording = {
        "status": "warning",
        "log": "NOTE: SASHINY-BEGIN run=fixture;\nWARNING: something\n",
        "outputs": {"log": [{"text": "WARNING: something", "level": "warning"}]},
        "sas_version": "9.04.01M8",
    }
    (tmp_path / f"{key}.json").write_text(json.dumps(recording), encoding="utf-8")

    result = engine.run(contract, {}, today=TODAY)
    assert result.status == "warning"
    assert result.log == recording["log"]
    assert result.outputs == recording["outputs"]
    assert result.metadata["sas_version"] == "9.04.01M8"


def test_mock_engine_save_recording(tmp_path: Path) -> None:
    engine = MockEngine(recordings_dir=tmp_path)
    contract = _minimal_contract()
    macros: dict[str, str] = {}
    engine.save_recording(contract, macros, {"status": "success", "log": ""})
    key = _mock._recording_key(contract, macros)
    assert (tmp_path / f"{key}.json").is_file()


def test_mock_metadata_matches_r(tmp_path: Path) -> None:
    """#156: the package version as engine_version and R's timestamp form (spec §8.4)."""
    result = MockEngine().run(_minimal_contract(), {}, today=TODAY)
    assert result.metadata["engine_version"] == sashiny.__version__
    for k in ("started_at", "ended_at"):
        assert STAMP.match(result.metadata[k]), result.metadata[k]
    rec = json.loads(save_recording(tmp_path, "k", result).read_text(encoding="utf-8"))
    assert STAMP.match(rec["recorded_at"]), rec["recorded_at"]


def test_timestamps_are_utc_whole_seconds_and_old_forms_still_read() -> None:
    t0 = datetime(2024, 2, 29, 23, 59, 59, 750000, tzinfo=timezone.utc)
    r = sashiny.Result.new("r", "success", started_at=t0, ended_at=t0 + timedelta(seconds=2))
    assert r.metadata["started_at"] == "2024-02-29T23:59:59Z"
    assert r.metadata["ended_at"] == "2024-03-01T00:00:01Z"
    plus_one = timezone(timedelta(hours=1))
    assert utc_timestamp(datetime(2024, 3, 1, 1, 0, 0, tzinfo=plus_one)) == "2024-03-01T00:00:00Z"
    # Results written by Python up to 0.3.1 use "+00:00" with microseconds; both forms are read.
    old = sashiny.Result(
        run_id="r",
        status="success",
        metadata={
            "started_at": "1999-12-31T23:59:59.250000+00:00",
            "ended_at": "2000-01-01T00:00:01Z",
        },
    )
    assert "duration: 1.75 s" in repr(old)


def test_mock_and_recordings_are_not_public(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MockEngine", "save_recording", "load_recording"):
        assert not hasattr(sashiny, name)
    contract = _minimal_contract()
    engine = MockEngine()
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(RuntimeError, match="internal test fixture"):
        MockEngine()
    with pytest.raises(RuntimeError, match="internal test fixture"):
        engine.run(contract, {})
    with pytest.raises(TypeError, match=r"sashiny\.connect"):
        sashiny.run(contract, engine)
    with pytest.raises(TypeError, match=r"sashiny\.connect"):
        sashiny.Pool(engine)


def test_contract_sha256_hashes_yaml_not_program() -> None:
    """Spec §8: contract_sha256 is the YAML bytes; program_sha256 the program bytes."""
    path = repo_root() / "spec/fixtures/contracts/valid/minimal/contract.sashiny.yml"
    contract = sashiny.load(path)
    res = MockEngine().run(contract, {}, today=date(2026, 11, 11))
    assert res.metadata["contract_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    program = (path.parent / "program.sas").read_bytes()
    assert res.metadata["program_sha256"] == hashlib.sha256(program).hexdigest()
    assert res.metadata["contract_sha256"] != res.metadata["program_sha256"]


def test_mock_engine_reports_v014_for_missing_upload() -> None:
    """The mock engine runs §7 step-1 checks: a missing file is V014, not a crash."""
    contract = sashiny.load(FIX / "contracts" / "valid" / "dataset" / "contract.sashiny.yml")
    result = MockEngine().run(contract, {}, uploads={"adsl": "/nonexistent/path.csv"})
    assert result.status == "error"
    assert result.metadata["issues"] == [{"code": "V014", "message": "file not found: path.csv"}]


def test_mock_engine_reports_v014_for_bad_extension() -> None:
    contract = sashiny.load(FIX / "contracts" / "valid" / "dataset" / "contract.sashiny.yml")
    result = MockEngine().run(contract, {}, uploads={"adsl": "sample.txt"})
    assert result.status == "error"
    assert result.metadata["issues"][0]["code"] == "V014"
    assert "not accepted" in result.metadata["issues"][0]["message"]
