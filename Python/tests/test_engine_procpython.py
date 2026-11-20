"""Tests for the in-session PROC PYTHON engine (spec §6.5, §6.6; #128).

A test-only fake stands in for the ``SAS`` object PROC PYTHON injects. Like the
real callback, its ``submit`` returns nothing: the engine routes the log and the
listing to WORK files with ``PROC PRINTTO`` / ``ODS HTML5`` and reads them back.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

import sashiny
from _repo import repo_root
from fakesas import FakeSAS
from sashiny.engines.procpython import DEAD_MESSAGE, RESET_REFUSED

FIX = repo_root() / "spec" / "fixtures" / "contracts" / "valid"
_PRINTTO = re.compile(r'proc printto log="([^"]+)" new; run;')
_ODS = re.compile(r'ods html5 file="([^"]+)"')


class FakeCallback:
    """The PROC PYTHON ``SAS`` object: submit writes files, sd2df/df2sd take ``lib.mem``."""

    def __init__(self, work: Path, inner: FakeSAS | None = None, delay: float = 0) -> None:
        self.work = work
        self.inner = inner or FakeSAS()
        self.delay = delay
        self.submitted: list[str] = []
        self.symbols: dict[str, str] = {}

    def submit(self, code: str) -> None:
        self.submitted.append(code)
        if "%let _sashiny_work=" in code:
            self.symbols["_sashiny_work"] = str(self.work)
            return
        if "SASHINY-BEGIN run=" in code and self.delay:
            time.sleep(self.delay)
        log = _PRINTTO.search(code)
        lst = _ODS.search(code)
        body = code
        for pat in (_PRINTTO, _ODS):
            body = pat.sub("", body)
        body = body.replace("ods html5 close;", "").replace("proc printto; run;", "").strip()
        out = self.inner.submit(body, results="HTML" if lst else "TEXT")
        if "SASHINY-PATH=" in body:
            out["LOG"] = out["LOG"].replace("/sas/work", str(self.work))
        if log:
            Path(log.group(1)).write_text(out.get("LOG", ""), encoding="utf-8")
        if lst:
            Path(lst.group(1)).write_text(out.get("LST", ""), encoding="utf-8")

    def symget(self, name: str) -> str:
        return self.symbols[name]

    def sd2df(self, name: str) -> Any:
        m = re.match(r"(\w+)\.(\w+)(?:\((.*)\))?$", name)
        assert m is not None
        opts: dict[str, Any] = {}
        if m.group(3):
            obs = re.search(r"obs=(\d+)", m.group(3))
            keep = re.search(r"keep=(.+)$", m.group(3))
            if obs:
                opts["obs"] = int(obs.group(1))
            if keep:
                opts["keep"] = keep.group(1).strip()
        return self.inner.sd2df(m.group(2), m.group(1), dsopts=opts or None)

    def df2sd(self, df: pd.DataFrame, name: str) -> None:
        lib, mem = name.split(".", 1)
        self.inner.df2sd(df, mem, lib, {})


def _contract(name: str, **run: Any) -> sashiny.Contract:
    contract = sashiny.load(FIX / name / "contract.sashiny.yml")
    if run:
        contract.data["run"] = {**(contract.data.get("run") or {}), **run}
    return contract


def test_requires_a_sas_object() -> None:
    with pytest.raises(TypeError, match="PROC PYTHON"):
        sashiny.connect_in_session(None)


def test_licence_acknowledgement_is_required(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.delenv("SASHINY_LICENSE_ACK", raising=False)
    cb = FakeCallback(tmp_path)
    eng = sashiny.connect_in_session(cb, own_session=True)
    res = eng.run(_contract("minimal"), {})
    assert res.status == "error"
    assert res.metadata["engine_error"].startswith("SAS licence not acknowledged")
    assert cb.submitted == []


def test_reset_work_needs_own_session(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path)
    eng = sashiny.connect_in_session(cb, license_ack=True)
    res = eng.run(_contract("minimal"), {})
    assert res.status == "error"
    assert res.metadata["engine_error"] == RESET_REFUSED
    assert cb.submitted == []


def test_run_without_reset_in_a_shared_session(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path)
    eng = sashiny.connect_in_session(cb, license_ack=True)
    res = eng.run(_contract("minimal", reset_work=False), {})
    assert res.status == "success", res.metadata
    assert res.metadata["engine"] == "procpython"
    assert res.metadata["backend"] == "in-session"
    assert not any("kill" in c for c in cb.submitted)
    assert not list(tmp_path.glob("_sashiny_*")), "temporary log/listing files are removed"


def test_own_session_runs_the_reset_and_reads_the_log(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path, FakeSAS(program_log="WARNING: Something odd."))
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    res = eng.run(_contract("minimal"), {})
    assert res.status == "warning"
    assert "WARNING: Something odd." in res.log
    assert any("proc datasets library=work kill" in c.lower() for c in cb.submitted)
    main = next(c for c in cb.submitted if "SASHINY-BEGIN run=" in c)
    assert main.startswith('proc printto log="')
    assert 'ods html5 file="' in main


def test_error_in_log_is_an_error(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path, FakeSAS(program_log="ERROR: Variable X not found.", syscc=8))
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    assert eng.run(_contract("minimal"), {}).status == "error"


def test_invalid_values_never_reach_sas(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path)
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    res = eng.run(_contract("numeric"), {"min_msrp": 999999, "ratio": 0.5})
    assert res.status == "error"
    assert {i["code"] for i in res.metadata["issues"]} == {"V003"}
    assert not any("SASHINY-BEGIN" in c for c in cb.submitted)


def test_tables_are_collected(tmp_path: Path) -> None:
    contract = sashiny.load(FIX / "outputs" / "contract.sashiny.yml")
    tables = [o for o, s in contract.data["outputs"].items() if s["type"] == "table"]
    if not tables:
        pytest.skip("fixture has no table output")
    ref = contract.data["outputs"][tables[0]]["from"]
    lib, mem = ref.split(".", 1) if "." in ref else ("WORK", ref)
    frame = pd.DataFrame({"origin": ["Asia", "USA"], "mean_msrp": [1.0, 2.0], "hp": [1.0, 2.0]})
    inner = FakeSAS({(lib.upper(), mem.upper()): frame})
    cb = FakeCallback(tmp_path, inner)
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    res = eng.run(contract, {})
    value = res.outputs[tables[0]]
    assert "error" not in value, value
    assert len(value["rows"]) == 2


def test_timeout_stops_the_engine(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path, delay=2.0)
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    res = eng.run(_contract("minimal", timeout_seconds=1), {})
    assert res.status == "error"
    assert res.metadata["engine_error"].startswith("run exceeded timeout_seconds")
    again = eng.run(_contract("minimal"), {})
    assert again.metadata["engine_error"] == DEAD_MESSAGE


def test_close_never_ends_the_parent_session(tmp_path: Path) -> None:
    cb = FakeCallback(tmp_path)
    eng = sashiny.connect_in_session(cb, license_ack=True, own_session=True)
    eng.run(_contract("minimal"), {})
    eng.close()
    assert not cb.inner.ended


def test_public_entry_points_accept_it_but_pools_do_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    eng = sashiny.connect_in_session(FakeCallback(tmp_path), license_ack=True, own_session=True)
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    from sashiny.engines.base import check_engine  # noqa: PLC0415

    assert check_engine(eng) is eng
    with pytest.raises(TypeError, match="cannot be pooled"):
        sashiny.Pool(eng)
