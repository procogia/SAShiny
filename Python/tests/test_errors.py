"""Exception hierarchy, Result.__repr__ and Result.check() (#130 H5)."""

from __future__ import annotations

from pathlib import Path

import pytest

import sashiny
from _repo import repo_root
from sashiny import deploy as d
from sashiny.engines.base import check_engine
from sashiny.result import failure_reason
from sashiny.upload import UploadError

FIX = repo_root() / "spec" / "fixtures"


def _result(status: str = "success", log: str = "", **meta: object) -> sashiny.Result:
    r = sashiny.Result.new("r-123", status)
    r.log = log
    r.metadata.update({"engine": "mock", "backend": "oda", "seconds": 1.5, **meta})
    return r


def test_every_kind_is_a_sashiny_error_and_its_builtin() -> None:
    assert issubclass(sashiny.ContractError, ValueError)
    assert issubclass(sashiny.ValuesError, ValueError)
    assert issubclass(sashiny.EngineError, TypeError)
    assert issubclass(sashiny.LicenseError, RuntimeError)
    assert issubclass(sashiny.DeployError, ValueError)
    assert issubclass(sashiny.RunError, RuntimeError)
    assert issubclass(UploadError, sashiny.SashinyError)
    assert UploadError is sashiny.UploadError
    with pytest.raises(sashiny.DeployError):
        d.deploy(".", "nope", license_ack=True)


def test_engine_check_raises_engine_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST")
    with pytest.raises(sashiny.EngineError, match="engine must come from"):
        check_engine(object())  # type: ignore[arg-type]


def test_invalid_contract_names_file_and_paths(tmp_path: Path) -> None:
    (tmp_path / "p.sas").write_text("data a; run;\n", encoding="utf-8")
    (tmp_path / "cars.sashiny.yml").write_text(
        "sashiny: 1\nprogram: p.sas\ntitle: Cars\ninputs:\n  min_msrp:\n    type: numeric\n"
        "    label: Min\n    min: 10\n    max: 1\noutputs:\n  log:\n    type: log\n",
        encoding="utf-8",
    )
    contract = sashiny.load(tmp_path / "cars.sashiny.yml")
    with pytest.raises(sashiny.ContractError) as info:
        sashiny.validate(contract, raise_error=True)
    assert "cars.sashiny.yml is invalid" in str(info.value)
    assert "/inputs/min_msrp" in str(info.value)
    assert info.value.issues
    good = sashiny.load(FIX / "contracts" / "valid" / "minimal" / "contract.sashiny.yml")
    assert sashiny.validate(good, raise_error=True) == []


def test_check_passes_and_raises() -> None:
    ok = _result()
    assert ok.check() is ok
    assert _result("warning").check().status == "warning"
    bad = _result("error", "NOTE: start\nERROR: File WORK.X does not exist.\nERROR: again\n")
    with pytest.raises(sashiny.RunError) as info:
        bad.check()
    assert str(info.value) == "run r-123 failed: ERROR: File WORK.X does not exist. (log line 2)"
    assert info.value.result is bad
    timeout = _result("error", engine_error="run exceeded timeout_seconds=1")
    with pytest.raises(sashiny.RunError, match="run exceeded timeout_seconds=1"):
        timeout.check()
    invalid = _result("error", issues=[{"code": "V003", "input": "/inputs/x"}])
    with pytest.raises(sashiny.RunError, match="invalid input V003 /inputs/x"):
        invalid.check()


def test_issue_without_input_id_gives_single_spaced_reason() -> None:
    """Mirrors R (#153): empty parts are skipped, never doubled spaces."""
    upload = _result("error", issues=[{"code": "V014", "input": "", "message": "no column AGE"}])
    assert failure_reason(upload) == "invalid input V014 no column AGE"
    with pytest.raises(sashiny.RunError) as info:
        upload.check()
    assert str(info.value) == "run r-123 failed: invalid input V014 no column AGE"
    assert failure_reason(_result("error", issues=[{"code": "V014"}])) == "invalid input V014"


def test_repr_matches_r_print() -> None:
    r = _result("error", "NOTE: a\nERROR: boom\n")
    r.outputs = {
        "stats": {
            "columns": [{"name": "n"}],
            "rows": [[1], [2]],
            "total_rows": 50,
            "truncated": True,
            "formatted": False,
        },
        "log": [{"level": "error", "text": "ERROR: boom"}],
        "report": "<html></html>",
        "csv": {"filename": "x.csv", "mime": "text/csv", "data": ""},
        "missing": {"error": "dataset WORK.NOPE not found"},
    }
    # Same text as R/tests/testthat/_snaps/errors.md (without colour).
    assert repr(r) == (
        "<sashiny result> error\n"
        "  run id:   r-123\n"
        "  duration: 1.50 s\n"
        "  backend:  oda\n"
        "  reason:   ERROR: boom (log line 2)\n"
        "  outputs:\n"
        "    stats: table, 2 row(s) of 50 x 1 column(s)\n"
        "    log: log, 1 line(s)\n"
        "    report: html, 13 characters\n"
        "    csv: download x.csv\n"
        "    missing: not collected: dataset WORK.NOPE not found"
    )
