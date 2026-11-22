"""Replay engine, registered engines and recordings (spec §6.6, §8.3)."""

from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import sashiny
from _repo import repo_root
from sashiny.engines.base import check_engine
from sashiny.modules import _status_text
from sashiny.recording import contract_sha256, key_for, program_sha256

REPLAY = repo_root() / "spec" / "fixtures" / "replay"
CASES = json.loads((REPLAY / "cases.json").read_text(encoding="utf-8"))
SAS_VERSION = "9.04.01M0P061913"


def _contract() -> sashiny.Contract:
    return sashiny.load(REPLAY / "replay.sashiny.yml")


def _copy_contract(tmp_path: Path) -> Path:
    folder = tmp_path / "app"
    folder.mkdir()
    for name in ("replay.sashiny.yml", "replay.sas"):
        shutil.copyfile(REPLAY / name, folder / name)
    return folder


class BatchEngine(sashiny.Engine):
    """A stand-in for an engine that runs on licensed SAS (the tests have no SAS)."""

    name = "test-batch"

    def run(
        self,
        contract: sashiny.Contract,
        values: dict[str, Any],
        *,
        today: date | None = None,
        uploads: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> sashiny.Result:
        macros, _ = sashiny.render_values(contract.data, values, today or date.today())
        return sashiny.engine_result(
            contract,
            "success",
            outputs={"log": [{"level": "note", "text": "NOTE: batch"}]},
            log="NOTE: SASHINY-BEGIN-PROGRAM\nNOTE: batch\nNOTE: SASHINY-END-PROGRAM\n",
            macros=macros,
            sas_version=SAS_VERSION,
            engine=self.name,
            run_id=run_id,
        )


def _outside_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run as if outside the test suite, so the public engine guard applies.

    Called in the test body: pytest sets ``PYTEST_CURRENT_TEST`` again for each
    test phase, so deleting it in a fixture would not last into the test.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST")


@pytest.fixture
def registered() -> Any:
    sashiny.register_engine(
        BatchEngine, license_ack=True, description="test stand-in for SAS 9.4 batch"
    )
    yield BatchEngine
    sashiny.unregister_engine(BatchEngine)


@pytest.mark.parametrize("case", CASES["cases"], ids=[c["name"] for c in CASES["cases"]])
def test_replay_matches_shared_fixture(
    case: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    _outside_tests(monkeypatch)
    engine = sashiny.replay(REPLAY / "recordings")
    result = sashiny.run(
        _contract(), engine, case["values"], today=date.fromisoformat(CASES["today"])
    )
    exp = case["expected"]
    meta = result.metadata
    assert result.status == exp["status"]
    assert meta.get("recording") == exp.get("recording")
    assert meta.get("engine_error") == exp.get("engine_error")
    assert meta.get("notice") == exp.get("notice")
    if "sas_version" in exp:
        assert meta["sas_version"] == exp["sas_version"]
        assert meta["recorded_at"] == exp["recorded_at"]
        assert meta["engine"] == "replay"
        assert meta["engine_version"] == sashiny.__version__
        assert result.log == exp["log"]
        assert result.outputs == exp["outputs"]
    if "issues" in exp:
        assert [{"code": i["code"], "input": i["input"]} for i in meta["issues"]] == exp["issues"]
    if exp.get("recording") in ("refused", "missing"):
        assert result.outputs == {}
        assert result.log == ""


def test_replayed_result_is_labelled_in_status_text() -> None:
    engine = sashiny.replay(REPLAY / "recordings")
    text = _status_text(sashiny.run(_contract(), engine, {"case": 1}))
    assert f"Replayed from {SAS_VERSION}, recorded 2015-07-30T12:00:00Z." in text
    refused = _status_text(sashiny.run(_contract(), engine, {"case": 2}))
    assert "engine error: recording not replayed: it has no SAS version" in refused


def test_replay_refuses_recording_of_changed_program(tmp_path: Path) -> None:
    folder = _copy_contract(tmp_path)
    with (folder / "replay.sas").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("/* changed */\n")
    contract = sashiny.load(folder / "replay.sashiny.yml")
    result = sashiny.run(contract, sashiny.replay(REPLAY / "recordings"), {"case": 1})
    assert result.status == "error"
    assert result.metadata["recording"] == "refused"
    assert result.metadata["engine_error"] == (
        "recording not replayed: it was made from a different version of the program"
    )


def test_replay_argument_and_repr() -> None:
    with pytest.raises(TypeError):
        sashiny.replay("")
    assert "replay engine" in repr(sashiny.replay("recs"))


def test_public_entry_points_accept_replay_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    _outside_tests(monkeypatch)
    pytest.importorskip("shiny")
    engine = sashiny.replay(REPLAY / "recordings")
    assert check_engine(engine) is engine
    assert sashiny.app([REPLAY / "replay.sashiny.yml"], engine) is not None
    assert isinstance(sashiny.Pool(engine), sashiny.Pool)


def test_unregistered_engine_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _outside_tests(monkeypatch)
    with pytest.raises(sashiny.EngineError, match=r"register_engine"):
        sashiny.run(_contract(), BatchEngine(), {"case": 1})
    with pytest.raises(sashiny.EngineError, match=r"register_engine"):
        sashiny.Pool(BatchEngine())


@pytest.mark.usefixtures("registered")
def test_registered_engine_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    _outside_tests(monkeypatch)
    pytest.importorskip("shiny")
    name = f"{BatchEngine.__module__}.{BatchEngine.__qualname__}"
    assert sashiny.registered_engines()[name] == "test stand-in for SAS 9.4 batch"
    result = sashiny.run(_contract(), BatchEngine(), {"case": 3})
    assert result.status == "success"
    assert result.metadata["engine"] == "test-batch"
    assert result.metadata["macros"] == {"CASE": "3"}
    assert result.metadata["engine_version"] == sashiny.__version__
    assert isinstance(sashiny.Pool(BatchEngine()), sashiny.Pool)
    assert sashiny.app([REPLAY / "replay.sashiny.yml"], BatchEngine()) is not None


def test_unregister_removes_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    _outside_tests(monkeypatch)
    sashiny.register_engine(BatchEngine, license_ack=True, description="x")
    sashiny.unregister_engine(BatchEngine)
    assert sashiny.registered_engines() == {}
    with pytest.raises(sashiny.EngineError):
        sashiny.run(_contract(), BatchEngine(), {"case": 1})


def test_registration_needs_explicit_ack_and_description(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SASHINY_LICENSE_ACK", "true")
    with pytest.raises(sashiny.LicenseError, match="SAS licence not acknowledged"):
        sashiny.register_engine(BatchEngine, description="x")
    with pytest.raises(sashiny.LicenseError):
        sashiny.register_engine(BatchEngine, license_ack="yes", description="x")  # type: ignore[arg-type]
    with pytest.raises(sashiny.EngineError, match="description"):
        sashiny.register_engine(BatchEngine, license_ack=True)
    with pytest.raises(sashiny.EngineError, match="description"):
        sashiny.register_engine(BatchEngine, license_ack=True, description="  ")
    with pytest.raises(sashiny.EngineError, match="SAShiny's own"):
        sashiny.register_engine(sashiny.ReplayEngine, license_ack=True, description="x")
    with pytest.raises(sashiny.EngineError, match="subclass"):
        sashiny.register_engine(dict, license_ack=True, description="x")
    assert sashiny.registered_engines() == {}


def test_engine_result_builds_metadata() -> None:
    contract = _contract()
    started = datetime(2015, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
    result = sashiny.engine_result(
        contract,
        "warning",
        log="WARNING: x\n",
        macros={"CASE": "1"},
        sas_version=SAS_VERSION,
        engine="batch",
        run_id="r1",
        started_at=started,
        ended_at="2015-07-30T12:00:05Z",
    )
    meta = result.metadata
    assert result.run_id == "r1"
    assert meta["status"] == "warning"
    assert meta["started_at"] == "2015-07-30T12:00:00Z"
    assert meta["ended_at"] == "2015-07-30T12:00:05Z"
    assert meta["contract_sha256"] == contract_sha256(contract)
    assert meta["program_sha256"] == program_sha256(contract)
    assert meta["engine_version"] == sashiny.__version__
    assert meta["collect_errors"] == []
    with pytest.raises(sashiny.EngineError):
        sashiny.engine_result(contract, "ok")


def test_record_then_replay_round_trip(tmp_path: Path) -> None:
    folder = _copy_contract(tmp_path)
    contract = sashiny.load(folder / "replay.sashiny.yml")
    live = BatchEngine().run(contract, {"case": 4})
    path = sashiny.record(tmp_path / "recs", contract, live)
    # The §8.3 key is unchanged: the same contract bytes and macros give the
    # file name the shared fixture uses for case 4.
    assert path.name == f"{key_for(contract, {'CASE': '4'}, {})}.json"
    assert (REPLAY / "recordings" / path.name).is_file()
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["sashiny_recording"] == 1
    assert rec["sas_version"] == SAS_VERSION
    assert rec["program_sha256"] == program_sha256(contract)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", rec["recorded_at"])
    replayed = sashiny.run(contract, sashiny.replay(tmp_path / "recs"), {"case": 4})
    assert replayed.metadata["recording"] == "replayed"
    assert replayed.log == live.log
    assert replayed.outputs == live.outputs
    assert (
        replayed.metadata["notice"]
        == f"Replayed from {SAS_VERSION}, recorded {rec['recorded_at']}."
    )


def test_record_writes_empty_macros_and_outputs_as_objects(tmp_path: Path) -> None:
    contract = sashiny.load(
        repo_root() / "spec/fixtures/contracts/valid/minimal/contract.sashiny.yml"
    )
    result = sashiny.engine_result(contract, "success", sas_version=SAS_VERSION)
    text = sashiny.record(tmp_path, contract, result).read_text(encoding="utf-8")
    assert '"macros": {}' in text
    assert '"outputs": {}' in text


def test_record_refuses_results_not_from_a_live_run(tmp_path: Path) -> None:
    folder = _copy_contract(tmp_path)
    contract = sashiny.load(folder / "replay.sashiny.yml")
    recs = tmp_path / "recs"
    ok = sashiny.engine_result(contract, "success", macros={"CASE": "1"}, sas_version=SAS_VERSION)
    no_version = sashiny.engine_result(contract, "success", macros={"CASE": "1"})
    with pytest.raises(sashiny.EngineError, match="no SAS version"):
        sashiny.record(recs, contract, no_version)
    replayed = sashiny.run(contract, sashiny.replay(REPLAY / "recordings"), {"case": 1})
    with pytest.raises(sashiny.EngineError, match="itself a replay"):
        sashiny.record(recs, contract, replayed)
    hit = sashiny.engine_result(contract, "success", macros={"CASE": "1"}, sas_version=SAS_VERSION)
    hit.metadata["cache_hit"] = True
    with pytest.raises(sashiny.EngineError, match="cache hit"):
        sashiny.record(recs, contract, hit)
    other = sashiny.engine_result(contract, "success", sas_version=SAS_VERSION)
    other.metadata["contract_sha256"] = "0" * 64
    with pytest.raises(sashiny.EngineError, match="different contract"):
        sashiny.record(recs, contract, other)
    with (folder / "replay.sas").open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("/* changed */\n")
    with pytest.raises(sashiny.EngineError, match="different version of the program"):
        sashiny.record(recs, contract, ok)
    assert not recs.exists()
