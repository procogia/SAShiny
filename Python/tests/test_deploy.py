"""Conformance tests for deployment targets (spec §6.8, spec/fixtures/deploy)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

import sashiny
from _repo import repo_root
from sashiny import deploy as d

FIX = repo_root() / "spec" / "fixtures" / "deploy"
CASES = sorted(p.parent.name for p in FIX.glob("*/case.json"))


def _profile_cases() -> list[dict[str, Any]]:
    return json.loads((FIX / "profiles.json").read_text(encoding="utf-8"))["cases"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("case", _profile_cases(), ids=lambda c: c["name"])
def test_profile_fixture(case: dict[str, Any]) -> None:
    if "expected_error" in case:
        with pytest.raises(ValueError, match="^" + case["expected_error"]):
            sashiny.parse_profile(case["profile"])
        return
    p = sashiny.parse_profile(case["profile"])
    exp = case["expected"]
    assert p.kind == exp["kind"]
    assert p.endpoints == exp["endpoints"]
    assert p.needs_java is exp["needs_java"]
    assert p.requires_vpn is exp["requires_vpn"]
    assert [list(e) for e in p.env] == exp["env"]
    assert p.secrets == exp["secrets"]


def _staged_app(case_dir: Path, tmp_path: Path, add_files: dict[str, str]) -> Path:
    app = tmp_path / "app"
    shutil.copytree(case_dir / "app", app)
    for rel, text in add_files.items():
        f = app / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
    return app


@pytest.mark.parametrize("name", CASES)
def test_generate_fixture(name: str, tmp_path: Path) -> None:
    case_dir = FIX / name
    case = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
    app = _staged_app(case_dir, tmp_path, case.get("add_files", {}))
    out = tmp_path / "out"
    res = d.deploy(
        app,
        case["target"],
        out,
        case["profile"],
        license_ack=case["license_ack"],
        version=case["version"],
        **case["options"],
    )
    exp = case["expected"]
    assert res.language == exp["language"]
    assert res.files == exp["files"]
    assert res.excluded == exp["excluded"]
    assert [list(e) for e in res.env] == exp["env"]
    assert res.secrets == exp["secrets"]
    assert res.endpoints == exp["endpoints"]
    written = sorted(str(p.relative_to(out).as_posix()) for p in out.rglob("*") if p.is_file())
    assert written == exp["files"]
    for want in (case_dir / "expected").rglob("*"):
        if want.is_file():
            rel = want.relative_to(case_dir / "expected")
            assert (out / rel).read_bytes() == want.read_bytes(), rel
    # No secret file or credential value leaks into the output.
    for f in out.rglob("*"):
        if f.is_file():
            assert "placeholder credential" not in f.read_text(encoding="utf-8", errors="ignore")


def _error_cases() -> list[dict[str, Any]]:
    return json.loads((FIX / "errors.json").read_text(encoding="utf-8"))["cases"]  # type: ignore[no-any-return]


@pytest.mark.parametrize("case", _error_cases(), ids=lambda c: c["name"])
def test_error_fixture(case: dict[str, Any], tmp_path: Path) -> None:
    app = _staged_app(FIX / Path(case["app"]).parent, tmp_path, {})

    def run() -> d.DeployResult:
        return d.deploy(
            app,
            case["target"],
            tmp_path / "out",
            case["profile"],
            license_ack=case["license_ack"],
            version="0.0.0",
            **case["options"],
        )

    if case["expected_error"] is None:
        assert run().files
    else:
        with pytest.raises(ValueError, match="^" + case["expected_error"]):
            run()


def test_out_dir_must_be_empty(tmp_path: Path) -> None:
    app = _staged_app(FIX / "vpn_rejected", tmp_path, {})
    out = tmp_path / "out"
    out.mkdir()
    (out / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="out_dir must be empty"):
        d.deploy(
            app,
            "container",
            out,
            {"name": "oda", "method": "iom", "oda_region": "us1"},
            license_ack=True,
        )


def test_registry_lists_container() -> None:
    ids = [t.id for t in d.targets()]
    assert "container" in ids
    assert sashiny.deploy.targets() == d.targets()


def test_doctor_reports_names_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert d.doctor("container") == ["docker is not on PATH (needed only to build)"]
    with pytest.raises(ValueError, match="unknown deployment target"):
        d.doctor("heroku")


def test_connect_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("SASHINY_PROFILE", "SASHINY_ODA_REGION", "SASHINY_VIYA_URL", "SASHINY_SAS94_HOST"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValueError, match="SASHINY_PROFILE"):
        sashiny.connect_from_env()
    monkeypatch.setenv("SASHINY_PROFILE", "oda")
    monkeypatch.setenv("SASHINY_ODA_REGION", "eu1")
    assert sashiny.connect_from_env().backend == "oda"
    monkeypatch.setenv("SASHINY_PROFILE", "viya")
    with pytest.raises(ValueError, match="SASHINY_VIYA_URL"):
        sashiny.connect_from_env()
    monkeypatch.setenv("SASHINY_VIYA_URL", "https://viya.example.com")
    assert sashiny.connect_from_env().backend == "viya"
    monkeypatch.setenv("SASHINY_PROFILE", "sas94")
    monkeypatch.setenv("SASHINY_SAS94_HOST", "sas94.example.com")
    monkeypatch.setenv("SASHINY_SAS94_PORT", "8592")
    engine = sashiny.connect_from_env(license_ack=True)
    assert engine.backend == "sas94-iom"
    assert engine.cfg["iomport"] == 8592  # type: ignore[index]
