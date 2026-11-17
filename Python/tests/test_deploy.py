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


def test_azure_apply_runs_commands_through_runner(tmp_path: Path) -> None:
    app = _staged_app(FIX / "azure_python_oda", tmp_path, {})
    calls: list[list[str]] = []

    def runner(args, env):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        return 0

    res = d.deploy(
        app,
        "azure_container_apps",
        tmp_path / "out",
        {"name": "oda", "method": "iom", "oda_region": "us1"},
        license_ack=True,
        apply=True,
        runner=runner,
        resource_group="rg1",
        acr_name="myacr",
        image_tag="v1",
        sas_user_secret_uri="https://kv.vault.azure.net/secrets/sashiny-sas-user",  # noqa: S106
        sas_password_secret_uri="https://kv.vault.azure.net/secrets/sashiny-sas-password",  # noqa: S106
    )
    out = str(res.out_dir)
    assert calls[0] == [
        "az",
        "acr",
        "build",
        "--registry",
        "myacr",
        "--image",
        "sashiny-app:v1",
        out,
    ]
    assert calls[1][:6] == ["az", "deployment", "group", "create", "--resource-group", "rg1"]
    assert "acrName=myacr" in calls[1]
    assert res.commands == calls


def test_azure_apply_requires_options_and_stops_on_failure(tmp_path: Path) -> None:
    app = _staged_app(FIX / "azure_python_oda", tmp_path, {})
    prof = {"name": "oda", "method": "iom", "oda_region": "us1"}
    with pytest.raises(ValueError, match="apply needs the options resource_group, acr_name"):
        d.deploy(
            app,
            "azure_container_apps",
            tmp_path / "o1",
            prof,
            license_ack=True,
            apply=True,
            runner=lambda a, e: 0,
        )
    with pytest.raises(RuntimeError, match="exit status 1"):
        d.deploy(
            app,
            "azure_container_apps",
            tmp_path / "o2",
            prof,
            license_ack=True,
            apply=True,
            runner=lambda a, e: 1,
            resource_group="rg",
            acr_name="a",
            sas_user_secret_uri="u",  # noqa: S106
            sas_password_secret_uri="p",  # noqa: S106
        )


def test_azure_options_are_validated(tmp_path: Path) -> None:
    app = _staged_app(FIX / "azure_python_oda", tmp_path, {})
    prof = {"name": "oda", "method": "iom", "oda_region": "us1"}
    with pytest.raises(ValueError, match="app_name must be"):
        d.deploy(
            app,
            "azure_container_apps",
            tmp_path / "o1",
            prof,
            license_ack=True,
            app_name="Bad_Name",
        )
    with pytest.raises(ValueError, match="max_replicas must be"):
        d.deploy(
            app, "azure_container_apps", tmp_path / "o2", prof, license_ack=True, max_replicas=0
        )
    vpn = {"name": "v", "method": "http", "url": "https://v.example.com", "requires_vpn": True}
    with pytest.raises(
        ValueError, match=r"^profile v requires a private network; pass infrastructure_subnet_id"
    ):
        d.deploy(app, "azure_container_apps", tmp_path / "o3", vpn, license_ack=True)


def test_azure_ssh_profile_has_no_secrets(tmp_path: Path) -> None:
    app = _staged_app(FIX / "azure_python_oda", tmp_path, {})
    prof = {"name": "s", "method": "ssh", "host": "h.example.com", "saspath": "/opt/sas/sas"}
    res = d.deploy(app, "azure_container_apps", tmp_path / "o", prof, license_ack=True)
    bicep = (res.out_dir / "infra" / "main.bicep").read_text(encoding="utf-8")
    assert "secrets:" not in bicep
    assert "SecretUri" not in bicep
    assert "keyvault" not in (res.out_dir / "deploy-azure.md").read_text(encoding="utf-8")


def test_azure_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert d.doctor("azure_container_apps") == ["az (Azure CLI) is not on PATH"]
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/az")
    assert d.doctor("azure_container_apps", runner=lambda a, e: 1) == [
        "az is not logged in (run az login)"
    ]
    assert d.doctor("azure_container_apps", runner=lambda a, e: 0) == []


def test_aws_apply_runs_commands_through_runner(tmp_path: Path) -> None:
    app = _staged_app(FIX / "aws_python_oda", tmp_path, {})
    calls: list[list[str]] = []

    def runner(args, env):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        return 0

    image = "1.dkr.ecr.us-east-1.amazonaws.com/sashiny-app:v1"
    res = d.deploy(
        app,
        "aws_ecs_express",
        tmp_path / "out",
        {"name": "oda", "method": "iom", "oda_region": "us1"},
        license_ack=True,
        apply=True,
        runner=runner,
        image_uri=image,
        vpc_id="vpc-1",
        public_subnet_ids=["subnet-a", "subnet-b"],
        private_subnet_ids="subnet-c,subnet-d",
        certificate_arn="arn:aws:acm:us-east-1:1:certificate/x",
        sas_user_secret_arn="arn:aws:secretsmanager:us-east-1:1:secret:u",  # noqa: S106
        sas_password_secret_arn="arn:aws:secretsmanager:us-east-1:1:secret:p",  # noqa: S106
    )
    out = str(res.out_dir)
    assert calls[0] == ["docker", "build", "--platform", "linux/amd64", "-t", image, out]
    assert calls[1] == ["docker", "push", image]
    assert calls[2][:5] == ["aws", "cloudformation", "deploy", "--stack-name", "sashiny-app"]
    assert "PublicSubnetIds=subnet-a,subnet-b" in calls[2]
    assert "SasPasswordSecretArn=arn:aws:secretsmanager:us-east-1:1:secret:p" in calls[2]
    assert res.commands == calls


def test_aws_apply_and_options_are_validated(tmp_path: Path) -> None:
    app = _staged_app(FIX / "aws_python_oda", tmp_path, {})
    prof = {"name": "oda", "method": "iom", "oda_region": "us1"}
    with pytest.raises(ValueError, match="apply needs the options image_uri, vpc_id"):
        d.deploy(
            app,
            "aws_ecs_express",
            tmp_path / "o1",
            prof,
            license_ack=True,
            apply=True,
            runner=lambda a, e: 0,
        )
    with pytest.raises(ValueError, match="desired_count must be"):
        d.deploy(app, "aws_ecs_express", tmp_path / "o2", prof, license_ack=True, desired_count=11)
    vpn = {"name": "v", "method": "http", "url": "https://v.example.com", "requires_vpn": True}
    with pytest.raises(ValueError, match="pass private_network for target aws_ecs_express"):
        d.deploy(app, "aws_ecs_express", tmp_path / "o3", vpn, license_ack=True)


def test_aws_ssh_profile_has_no_secrets(tmp_path: Path) -> None:
    app = _staged_app(FIX / "aws_python_oda", tmp_path, {})
    prof = {"name": "s", "method": "ssh", "host": "h.example.com", "saspath": "/opt/sas/sas"}
    res = d.deploy(app, "aws_ecs_express", tmp_path / "o", prof, license_ack=True)
    text = (res.out_dir / "infra" / "template.yaml").read_text(encoding="utf-8")
    assert "SecretArn" not in text
    assert "Secrets:" not in text
    assert "FromPort: 22\n" in text
    guide = (res.out_dir / "deploy-aws.md").read_text(encoding="utf-8")
    assert "secretsmanager" not in guide
    assert "## 1. Build and push the image" in guide


def test_aws_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert d.doctor("aws_ecs_express") == ["aws (AWS CLI) is not on PATH"]
    monkeypatch.setattr(shutil, "which", lambda n: None if n == "docker" else "/usr/bin/aws")
    assert d.doctor("aws_ecs_express", runner=lambda a, e: 255) == [
        "aws has no valid credentials (run aws configure or aws sso login)"
    ]
    assert d.doctor("aws_ecs_express", runner=lambda a, e: 0) == ["docker is not on PATH"]


def test_snowflake_apply_runs_commands_through_runner(tmp_path: Path) -> None:
    app = _staged_app(FIX / "snowflake_python_oda", tmp_path, {})
    calls: list[list[str]] = []

    def runner(args, env):  # type: ignore[no-untyped-def]
        calls.append(list(args))
        return 0

    res = d.deploy(
        app,
        "snowflake_spcs",
        tmp_path / "out",
        {"name": "oda", "method": "iom", "oda_region": "us1"},
        license_ack=True,
        apply=True,
        runner=runner,
        repository_url="org-acct.registry.snowflakecomputing.com/sashiny_db/app/sashiny_repo/",
        connection="dev",
    )
    out = str(res.out_dir)
    image = (
        "org-acct.registry.snowflakecomputing.com/sashiny_db/app/sashiny_repo/sashiny-app:latest"
    )
    assert calls == [
        ["snow", "sql", "-f", f"{out}/spcs/setup.sql", "--connection", "dev"],
        ["snow", "spcs", "image-registry", "login", "--connection", "dev"],
        ["docker", "build", "--platform", "linux/amd64", "-t", image, out],
        ["docker", "push", image],
        ["snow", "sql", "-f", f"{out}/spcs/service.sql", "--connection", "dev"],
    ]


def test_snowflake_options_are_validated(tmp_path: Path) -> None:
    app = _staged_app(FIX / "snowflake_python_oda", tmp_path, {})
    prof = {"name": "oda", "method": "iom", "oda_region": "us1"}
    with pytest.raises(ValueError, match="apply needs the options repository_url"):
        d.deploy(
            app,
            "snowflake_spcs",
            tmp_path / "o1",
            prof,
            license_ack=True,
            apply=True,
            runner=lambda a, e: 0,
        )
    with pytest.raises(ValueError, match="database must be 1-63 uppercase"):
        d.deploy(
            app, "snowflake_spcs", tmp_path / "o2", prof, license_ack=True, database="db; DROP"
        )
    with pytest.raises(ValueError, match="instances must be"):
        d.deploy(app, "snowflake_spcs", tmp_path / "o3", prof, license_ack=True, instances=0)
    vpn = {"name": "v", "method": "http", "url": "https://v.example.com", "requires_vpn": True}
    with pytest.raises(ValueError, match="pass private_connectivity for target snowflake_spcs"):
        d.deploy(app, "snowflake_spcs", tmp_path / "o4", vpn, license_ack=True)


def test_snowflake_ssh_profile_has_no_secret(tmp_path: Path) -> None:
    app = _staged_app(FIX / "snowflake_python_oda", tmp_path, {})
    prof = {"name": "s", "method": "ssh", "host": "h.example.com", "saspath": "/opt/sas/sas"}
    res = d.deploy(app, "snowflake_spcs", tmp_path / "o", prof, license_ack=True, public=False)
    assert "spcs/secret.sql" not in res.files
    spec = (res.out_dir / "spcs" / "service-spec.yaml").read_text(encoding="utf-8")
    assert "secrets:" not in spec
    assert "public: false" in spec
    guide = (res.out_dir / "deploy-snowflake-spcs.md").read_text(encoding="utf-8")
    assert "## 2. Build and push the image" in guide


def test_snowflake_doctor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert d.doctor("snowflake_spcs") == ["snow (Snowflake CLI) is not on PATH"]
    monkeypatch.setattr(shutil, "which", lambda n: None if n == "docker" else "/usr/bin/snow")
    assert d.doctor("snowflake_spcs", runner=lambda a, e: 1) == [
        "snow has no working connection (run snow connection add)"
    ]
    assert d.doctor("snowflake_spcs", runner=lambda a, e: 0) == ["docker is not on PATH"]
