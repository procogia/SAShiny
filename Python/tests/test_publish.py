"""Tests for publishing to Posit Connect (spec §6.7). No network: the CLI is stubbed."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

import pytest

import sashiny
from engines_helper import MockEngine
from sashiny.errors import DeployError
from sashiny.publish import on_connect, publish

SECRETS = [".authinfo", "_authinfo", ".Renviron", ".env", "server.pem", "data/id.key"]


@pytest.fixture
def app_dir(tmp_path: Path) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / ".git").mkdir()
    (tmp_path / "app.py").write_text("import sashiny\n", encoding="utf-8")
    (tmp_path / "prog.sas").write_text("proc print; run;\n", encoding="utf-8")
    (tmp_path / "data" / "x.csv").write_text("a,b\n", encoding="utf-8")
    (tmp_path / ".git" / "HEAD").write_text("ref\n", encoding="utf-8")
    for name in SECRETS:
        (tmp_path / name).write_text("secret\n", encoding="utf-8")
    return tmp_path


class Recorder:
    def __init__(self) -> None:
        self.args: list[str] = []
        self.env: dict[str, str] = {}
        self.staged: list[str] = []

    def __call__(self, args: Sequence[str], env: dict[str, str]) -> None:
        self.args = list(args)
        self.env = env
        staged = Path(args[2])
        self.staged = sorted(
            p.relative_to(staged).as_posix() for p in staged.rglob("*") if p.is_file()
        )


def test_publish_bundles_no_credentials_and_sends_names_only(
    app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SASHINY_SAS_USER", "me")
    monkeypatch.setenv("SASHINY_SAS_PASSWORD", "s3cret-Pa55")
    monkeypatch.delenv("SASHINY_LICENSE_ACK", raising=False)
    rec = Recorder()
    res = publish(app_dir, title="Demo", server="srv", license_ack=True, runner=rec)
    assert sorted(res.files) == ["app.py", "data/x.csv", "prog.sas"]
    assert sorted(res.excluded) == sorted(SECRETS)
    assert rec.staged == ["app.py", "data/x.csv", "prog.sas"]
    assert res.env_vars == ["SASHINY_LICENSE_ACK", "SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD"]
    assert rec.args[:2] == ["deploy", "shiny"]
    assert rec.args[3:5] == ["--name", "srv"]
    assert "s3cret-Pa55" not in " ".join(rec.args)
    assert rec.env["SASHINY_LICENSE_ACK"] == "true"
    assert "SASHINY_LICENSE_ACK" not in os.environ


def test_publish_name_is_the_content_name_as_in_r(
    app_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # R's sas_publish(name = ) is the content name; rsconnect-python derives the
    # content name from the bundle directory when no title is given.
    monkeypatch.setenv("SASHINY_SAS_USER", "me")
    monkeypatch.setenv("SASHINY_SAS_PASSWORD", "pw")
    rec = Recorder()
    publish(app_dir, name="cars-explorer", license_ack=True, runner=rec)
    assert Path(rec.args[2]).name == "cars-explorer"
    assert "--name" not in rec.args
    assert "--title" not in rec.args

    rec = Recorder()
    publish(app_dir, license_ack=True, runner=rec)
    assert Path(rec.args[2]).name == app_dir.name

    with pytest.warns(UserWarning, match="content name follows title"):
        publish(app_dir, name="cars", title="Cars", license_ack=True, runner=Recorder())
    with pytest.raises(DeployError, match="plain content name"):
        publish(app_dir, name="../x", license_ack=True, runner=Recorder())


def test_publish_refuses_without_ack_or_credentials(
    app_dir: Path, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    def never(args: Sequence[str], env: dict[str, str]) -> None:
        raise AssertionError("must not deploy")

    with pytest.raises(ValueError, match="license_ack=True"):
        publish(app_dir, runner=never)
    monkeypatch.delenv("SASHINY_SAS_USER", raising=False)
    with pytest.raises(ValueError, match="SASHINY_SAS_USER"):
        publish(app_dir, license_ack=True, runner=never)
    empty = tmp_path_factory.mktemp("empty")
    with pytest.raises(ValueError, match=r"app\.py"):
        publish(empty, license_ack=True, sas_credentials="server", runner=never)


def test_on_connect_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RSTUDIO_PRODUCT", "CONNECT_SERVER_URL", "CONNECT_CONTENT_GUID"):
        monkeypatch.delenv(var, raising=False)
    assert not on_connect()
    monkeypatch.setenv("RSTUDIO_PRODUCT", "CONNECT")
    assert on_connect()


def test_publish_tab_is_opt_in_and_hidden_on_connect(monkeypatch: pytest.MonkeyPatch) -> None:
    pytest.importorskip("shiny")
    from _repo import repo_root  # noqa: PLC0415

    path = repo_root() / "spec/fixtures/contracts/valid/minimal/contract.sashiny.yml"
    for var in ("RSTUDIO_PRODUCT", "CONNECT_SERVER_URL", "CONNECT_CONTENT_GUID"):
        monkeypatch.delenv(var, raising=False)

    def html(app: object) -> str:
        return str(app.ui["html"])  # type: ignore[attr-defined]

    assert "Publish to Posit Connect" not in html(sashiny.app([path], MockEngine()))
    assert "Publish to Posit Connect" in html(sashiny.app([path], MockEngine(), publish=True))
    monkeypatch.setenv("RSTUDIO_PRODUCT", "CONNECT")
    assert "Publish to Posit Connect" not in html(sashiny.app([path], MockEngine(), publish=True))
