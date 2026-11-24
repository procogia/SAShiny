"""End-to-end tests of SaspyEngine against a fake saspy session (spec §6-§8)."""

from __future__ import annotations

import base64
import datetime as dt
import json
import time
from datetime import date
from pathlib import Path
from threading import Event

import pytest

import sashiny
from engines_helper import MockEngine, fake_engine, save_recording
from sashiny.engines import saspy as saspy_mod
from sashiny.engines.saspy import SaspyEngine, _sas_number, _write_cfgfile

pd = pytest.importorskip("pandas")
from fakesas import FakeSAS  # noqa: E402

TODAY = date(2026, 11, 11)

CONTRACT = """\
sashiny: 1
program: prog.sas
title: Fake run
inputs:
  min_age:
    type: numeric
    label: Minimum age
    default: 18
  make:
    type: choice
    label: Make
    choices_from: {dataset: sashelp.cars, value_column: make}
    optional: true
  adsl:
    type: dataset
    label: ADSL
    target: work.adsl
    sample: adsl.csv
    optional: true
    columns:
      - {name: age, type: numeric}
outputs:
  stats:
    type: table
    from: work.stats
    columns: [AGE, name]
    max_rows: 2
  stats_fmt:
    type: table
    from: work.stats
    formatted: true
  missing:
    type: table
    from: work.nope
  graphs:
    type: plot
  second:
    type: plot
    select: 2
  report:
    type: html
  log:
    type: log
  csv:
    type: download
    format: csv
    from: work.stats
    filename: stats
  data:
    type: download
    format: sas7bdat
    from: work.stats
  rtf:
    type: download
    format: rtf
"""


@pytest.fixture
def contract(tmp_path: Path) -> sashiny.Contract:
    (tmp_path / "prog.sas").write_text("data work.stats; set work.adsl; run;\n", encoding="utf-8")
    (tmp_path / "adsl.csv").write_text("age,name\n40,Ann\n50,Bo\n", encoding="utf-8")
    path = tmp_path / "app.sashiny.yml"
    path.write_text(CONTRACT, encoding="utf-8")
    return sashiny.load(path)


def _fake() -> FakeSAS:
    stats = pd.DataFrame(
        {
            "name": ["Ann", "Bo", "Cy"],
            "age": [40.0, None, 61.0],
            "trtsdt": pd.to_datetime(["2024-01-02", None, "1960-01-01"]),
        }
    )
    cars = pd.DataFrame({"Make": ["BMW", "Audi", "BMW", "Saab"]})
    return FakeSAS(
        {("WORK", "STATS"): stats, ("SASHELP", "CARS"): cars},
        meta={("WORK", "STATS"): [{"name": "age", "label": "Age (y)", "format": "BEST12."}]},
        files={
            "/sas/work/stats.sas7bdat": b"SAS7BDAT",
            "/sas/work/sashiny_rtf.rtf": b"{\\rtf1}",
        },
    )


def _engine(fake: FakeSAS) -> SaspyEngine:
    return fake_engine(lambda: fake)


def test_run_without_licence_ack_never_reaches_sas(
    contract: sashiny.Contract, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Spec §6.6: no acknowledgement, no SAS session.
    opened: list[bool] = []
    engine = fake_engine(lambda: opened.append(True) or _fake(), license_ack=None)  # type: ignore[func-returns-value]
    monkeypatch.delenv("SASHINY_LICENSE_ACK", raising=False)
    result = engine.run(contract, {"min_age": 30}, today=TODAY)
    assert result.status == "error"
    assert result.metadata["engine_error"].startswith("SAS licence not acknowledged")
    assert opened == []
    monkeypatch.setenv("SASHINY_LICENSE_ACK", "TRUE")
    assert saspy_mod.license_acknowledged(None)
    assert not saspy_mod.license_acknowledged(False)


def test_new_session_turns_notes_on_first(contract: sashiny.Contract) -> None:
    # ODA starts sessions with NONOTES, which would hide the NOTE: sentinels (spec 6.1).
    fake = _fake()
    _engine(fake).run(contract, {"min_age": 30, "make": "BMW"}, today=TODAY)
    assert fake.submitted[0] == saspy_mod.SESSION_SETUP_CODE
    assert fake.submitted.count(saspy_mod.SESSION_SETUP_CODE) == 1


def test_dead_session_returns_connection_error_without_submitting(
    contract: sashiny.Contract,
) -> None:
    ended = Event()

    class Dead:
        SASpid = None

        def saslog(self) -> str:
            return "The workspace server rejected the connection."

        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            pytest.fail("a dead session must not receive setup or program code")

        def endsas(self) -> None:
            ended.set()

    sessions = iter((Dead(), _fake()))
    engine = fake_engine(lambda: next(sessions))
    result = engine.run(contract, {"min_age": 30}, today=TODAY)
    assert result.status == "error"
    assert "workspace server rejected the connection" in result.metadata["engine_error"]
    assert engine._sas is None
    assert ended.wait(1)
    assert engine.run(contract, {"min_age": 30}, today=TODAY).status == "success"


def test_full_run_collects_every_output(contract: sashiny.Contract) -> None:
    fake = _fake()
    engine = _engine(fake)
    result = engine.run(
        contract, {"min_age": 30, "make": "BMW"}, today=TODAY, uploads={"adsl": True}, run_id="r1"
    )
    assert result.status == "success"
    out = result.outputs

    assert out["stats"]["columns"][0] == {
        "name": "age",
        "type": "numeric",
        "label": "Age (y)",
        "format": "BEST12.",
    }
    assert [c["name"] for c in out["stats"]["columns"]] == ["age", "name"]
    assert out["stats"]["rows"] == [[40, "Ann"], [None, "Bo"]]
    assert out["stats"]["total_rows"] == 3
    assert out["stats"]["truncated"] is True

    assert out["stats_fmt"]["formatted"] is True
    assert out["stats_fmt"]["rows"][0][0] == "fmt:Ann"

    assert out["missing"] == {"error": "dataset WORK.NOPE not found"}
    assert result.metadata["collect_errors"] == ["missing: dataset WORK.NOPE not found"]

    assert [p["mime"] for p in out["graphs"]] == ["image/png", "image/svg+xml"]
    assert out["second"] == [out["graphs"][1]]
    assert out["report"].startswith("<html>")
    assert out["log"] == [
        {"level": "note", "text": "NOTE: The data set WORK.OUT has 2 observations."}
    ]

    assert out["csv"]["filename"] == "stats.csv"
    csv_text = base64.b64decode(out["csv"]["data"]).decode()
    assert csv_text.splitlines()[0] == "name,age,trtsdt"
    assert csv_text.splitlines()[1] == "Ann,40,23377"  # SAS date number
    assert base64.b64decode(out["data"]["data"]) == b"SAS7BDAT"
    assert out["data"]["filename"] == "data.sas7bdat"
    assert base64.b64decode(out["rtf"]["data"]) == b"{\\rtf1}"

    meta = result.metadata
    assert meta["sas_version"] == "9.04.01M8P011923"
    assert meta["macros"]["MIN_AGE"] == "30"
    assert meta["macros"]["MAKE"] == "BMW"
    assert len(meta["contract_sha256"]) == 64
    assert len(meta["program_sha256"]) == 64
    assert meta["syscc"] == 0

    # The sample was uploaded with the declared numeric column converted.
    df, _ = fake.uploaded[("WORK", "ADSL")]
    assert df["age"].tolist() == [40, 50]
    # Temporary members were cleaned up.
    assert not [k for k in fake.datasets if k[1].startswith("_SX_")]


PAIRED = """\
sashiny: 1
program: prog.sas
title: Paired
outputs:
  by_chart:
    type: chart
    from: work.stats
    columns: [name, age]
    sas_plot: 2
  by_plot:
    type: plot
    select: 1
    chart: {from: work.nope}
  bad_graph:
    type: chart
    from: work.stats
    sas_plot: 3
"""


def test_paired_outputs_collect_both_parts_independently(tmp_path: Path) -> None:
    # Spec §8.2 paired: each part is collected, and fails, on its own.
    (tmp_path / "prog.sas").write_text("data work.stats; run;\n", encoding="utf-8")
    path = tmp_path / "p.sashiny.yml"
    path.write_text(PAIRED, encoding="utf-8")
    result = _engine(_fake()).run(sashiny.load(path), {}, today=TODAY)
    out = result.outputs
    assert set(out["by_chart"]) == {"sas", "sashiny"}
    assert [p["mime"] for p in out["by_chart"]["sas"]] == ["image/svg+xml"]
    assert out["by_chart"]["sashiny"]["rows"][0] == ["Ann", 40]
    assert [p["mime"] for p in out["by_plot"]["sas"]] == ["image/png"]
    assert out["by_plot"]["sashiny"] == {"error": "dataset WORK.NOPE not found"}
    assert out["bad_graph"]["sas"] == {"error": "select=3 but the run produced 2 graph(s)"}
    assert out["bad_graph"]["sashiny"]["total_rows"] == 3
    assert result.metadata["collect_errors"] == [
        "by_plot.sashiny: dataset WORK.NOPE not found",
        "bad_graph.sas: select=3 but the run produced 2 graph(s)",
    ]


def test_choices_from_validation_uses_sas_choices(contract: sashiny.Contract) -> None:
    engine = _engine(_fake())
    assert engine.choices(contract) == {
        "make": [
            {"value": "Audi", "label": "Audi"},
            {"value": "BMW", "label": "BMW"},
            {"value": "Saab", "label": "Saab"},
        ]
    }
    bad = engine.run(contract, {"min_age": 30, "make": "Fiat"}, today=TODAY)
    assert bad.status == "error"
    assert bad.metadata["issues"][0]["code"].startswith("V")


def test_user_file_upload_and_upload_errors(contract: sashiny.Contract, tmp_path: Path) -> None:
    fake = _fake()
    engine = _engine(fake)
    own = tmp_path / "mine.csv"
    own.write_text("age\n33\n", encoding="utf-8")
    ok = engine.run(contract, {"min_age": 1}, today=TODAY, uploads={"adsl": own})
    assert ok.status == "success"
    assert fake.uploaded[("WORK", "ADSL")][0]["age"].tolist() == [33]

    bad = tmp_path / "bad.csv"
    bad.write_text("age\nold\n", encoding="utf-8")
    failed = engine.run(contract, {"min_age": 1}, today=TODAY, uploads={"adsl": bad})
    assert failed.status == "error"
    assert failed.metadata["issues"][0]["code"] == "V014"


def test_run_status_from_syscc(contract: sashiny.Contract) -> None:
    fake = _fake()
    fake.syscc = 4
    fake.program_log = "WARNING: Something."
    result = _engine(fake).run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "warning"


def test_broken_session_is_reported_and_replaced(contract: sashiny.Contract) -> None:
    calls = []

    class Dead(FakeSAS):
        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            if "SASHINY-BEGIN" in code:
                raise ConnectionError("lost connection")
            return super().submit(code, results)

    def factory() -> FakeSAS:
        calls.append(1)
        return Dead(_fake().datasets)

    engine = fake_engine(factory)
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "error"
    assert "lost connection" in result.metadata["engine_error"]
    engine.run(contract, {"min_age": 1}, today=TODAY)
    assert len(calls) == 2


def test_failed_session_is_closed_before_replacement(contract: sashiny.Contract) -> None:
    # A session that fails during a submission must be ended, not just dropped.
    ended: list[bool] = []

    class Dead(FakeSAS):
        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            if "SASHINY-BEGIN" in code:
                raise ConnectionError("lost connection")
            return super().submit(code, results)

        def endsas(self) -> None:
            ended.append(True)
            super().endsas()

    fake = Dead(_fake().datasets)
    engine = fake_engine(lambda: fake)
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "error"
    assert ended == [True]


def test_run_enforces_timeout_seconds(contract: sashiny.Contract) -> None:
    class Slow(FakeSAS):
        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            if "SASHINY-BEGIN" in code:
                time.sleep(1.2)
            return super().submit(code, results)

    fake = Slow(_fake().datasets)
    engine = fake_engine(lambda: fake)
    contract.data["run"] = {"timeout_seconds": 1}
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "error"
    assert "timeout" in result.metadata["engine_error"]
    assert fake.ended


def test_run_within_timeout_succeeds(contract: sashiny.Contract) -> None:
    engine = _engine(_fake())
    contract.data["run"] = {"timeout_seconds": 30}
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "success"


def test_live_runs_are_never_recorded(contract: sashiny.Contract) -> None:
    # Spec §6.6: live engines never write recordings.
    result = _engine(_fake()).run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "success"
    assert "recording" not in result.metadata
    assert result.metadata["backend"] == "sas94-iom"


def test_timeout_worker_does_not_reopen_session(contract: sashiny.Contract) -> None:
    # After a timeout, the worker must not call the factory again (issue #69).
    calls: list[int] = []

    class Slow(FakeSAS):
        def submit(self, code: str, results: str = "HTML") -> dict[str, str]:
            if "SASHINY-BEGIN" in code:
                time.sleep(1.2)
            return super().submit(code, results)

    def factory() -> FakeSAS:
        calls.append(1)
        return Slow(_fake().datasets)

    engine = fake_engine(factory)
    contract.data["run"] = {"timeout_seconds": 1}
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "error"
    assert "timeout" in result.metadata["engine_error"]
    # The worker's submit() returns after the timeout; give it a moment to
    # finish, then assert the factory was called exactly once (the initial
    # session), never again by the old worker.
    time.sleep(1.5)
    assert len(calls) == 1


def test_live_result_replays_through_test_mock(contract: sashiny.Contract, tmp_path: Path) -> None:
    rec = tmp_path / "recordings"
    live = _engine(_fake()).run(
        contract, {"min_age": 30, "make": "BMW"}, today=TODAY, uploads={"adsl": True}
    )
    path = save_recording(rec, contract, live, {"adsl": contract.base_dir / "adsl.csv"})
    assert json.loads(path.read_text(encoding="utf-8"))["sashiny_recording"] == 1

    mock = MockEngine(rec, choices={"make": ["BMW", "Audi"]})
    replay = mock.run(contract, {"min_age": 30, "make": "BMW"}, today=TODAY, uploads={"adsl": True})
    assert replay.metadata["recording"] == "replayed"
    assert replay.outputs == live.outputs
    assert replay.status == live.status

    other = mock.run(contract, {"min_age": 31, "make": "BMW"}, today=TODAY, uploads={"adsl": True})
    assert other.metadata["recording"] == "missing"
    assert other.outputs == {}


def test_close_ends_session(contract: sashiny.Contract) -> None:
    fake = _fake()
    engine = _engine(fake)
    engine.run(contract, {"min_age": 1}, today=TODAY)
    engine.close()
    assert fake.ended


def test_write_cfgfile(tmp_path: Path) -> None:
    path = _write_cfgfile({"java": "/usr/bin/java", "iomport": 8591}, "oda", tmp_path)
    namespace: dict[str, object] = {}
    exec(path.read_text(encoding="utf-8"), namespace)  # noqa: S102 - generated config
    assert namespace["SAS_config_names"] == ["oda"]
    assert namespace["oda"] == {"java": "/usr/bin/java", "iomport": 8591}
    with pytest.raises(ValueError, match="identifier"):
        _write_cfgfile({}, "not valid", tmp_path)


def test_sas_number_conversions() -> None:
    assert _sas_number(pd.Timestamp("1960-01-02"), "DATE9.") == 1
    assert _sas_number(pd.Timestamp("1960-01-01 00:01:00"), "DATETIME20.") == 60
    assert _sas_number(pd.Timestamp("2000-01-01 01:00:00"), "TIME8.") == 3600
    assert _sas_number(dt.date(1960, 1, 11), "") == 10
    assert _sas_number(dt.timedelta(seconds=90), "TIME8.") == 90
    assert _sas_number(5, "") == 5


def test_preflight_requires_java_for_iom() -> None:
    with pytest.raises(RuntimeError, match="Java was not found"):
        saspy_mod.preflight({"iomhost": ["h"], "java": None})
    saspy_mod.preflight({"url": "https://viya"})  # no authkey, no IOM: nothing to check


def test_preflight_requires_an_authinfo_entry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(saspy_mod, "authinfo_path", lambda: tmp_path / ".authinfo")
    with pytest.raises(RuntimeError, match="no credentials for 'oda'"):
        saspy_mod.preflight({"iomhost": ["h"], "java": "java", "authkey": "oda"})
    (tmp_path / ".authinfo").write_text("viya user a password b\noda user me password pw\n")
    saspy_mod.preflight({"iomhost": ["h"], "java": "java", "authkey": "oda"})


def test_missing_java_is_reported_on_the_result(contract: sashiny.Contract) -> None:
    engine = sashiny.SaspyEngine(
        {"iomhost": ["h"], "java": None, "authkey": "oda"}, license_ack=True
    )
    result = engine.run(contract, {"min_age": 1}, today=TODAY)
    assert result.status == "error"
    assert "Java was not found" in result.metadata["engine_error"]


def test_engine_reuses_one_session_across_runs(contract: sashiny.Contract) -> None:
    # Spec 6.5 (session lifetime): one engine, one SAS session, reused across runs.
    opened: list[FakeSAS] = []

    def factory() -> FakeSAS:
        opened.append(_fake())
        return opened[-1]

    engine = fake_engine(factory)
    results = [engine.run(contract, {"min_age": 30, "make": "BMW"}, today=TODAY) for _ in range(3)]
    assert [r.status for r in results] == ["success"] * 3
    assert len(opened) == 1
    assert opened[0].submitted.count(saspy_mod.SESSION_SETUP_CODE) == 1
