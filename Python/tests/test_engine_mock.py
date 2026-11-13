"""Tests for the mock engine (issue #5)."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import sashiny
from _repo import repo_root

SPEC = repo_root() / "spec"
FIX = SPEC / "fixtures"
TODAY = date(2026, 11, 11)


def _minimal_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")


def test_mock_engine_empty_success() -> None:
    engine = sashiny.MockEngine()
    contract = _minimal_contract()
    result = engine.run(contract, {}, today=TODAY)
    assert result.status == "success"
    assert result.run_id
    assert result.metadata["engine"] == "mock"


def test_mock_engine_invalid_values() -> None:
    engine = sashiny.MockEngine()
    contract = sashiny.load(FIX / "contracts" / "valid" / "numeric" / "contract.sashiny.yml")
    result = engine.run(contract, {"min_msrp": "not-a-number"}, today=TODAY)
    assert result.status == "error"


def test_mock_engine_replay(tmp_path: Path) -> None:
    engine = sashiny.MockEngine(recordings_dir=tmp_path)
    contract = _minimal_contract()
    # Save a recording for the empty-macros key.
    macros: dict[str, str] = {}
    key = sashiny.engines.mock._recording_key(contract, macros)
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
    engine = sashiny.MockEngine(recordings_dir=tmp_path)
    contract = _minimal_contract()
    macros: dict[str, str] = {}
    engine.save_recording(contract, macros, {"status": "success", "log": ""})
    key = sashiny.engines.mock._recording_key(contract, macros)
    assert (tmp_path / f"{key}.json").is_file()


def test_contract_sha256_hashes_yaml_not_program() -> None:
    """Spec §8: contract_sha256 is the YAML bytes; program_sha256 the program bytes."""
    path = repo_root() / "spec/fixtures/contracts/valid/minimal/contract.sashiny.yml"
    contract = sashiny.load(path)
    res = sashiny.MockEngine().run(contract, {}, today=date(2026, 11, 11))
    assert res.metadata["contract_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    program = (path.parent / "program.sas").read_bytes()
    assert res.metadata["program_sha256"] == hashlib.sha256(program).hexdigest()
    assert res.metadata["contract_sha256"] != res.metadata["program_sha256"]
