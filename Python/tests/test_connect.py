"""Tests for the SAS connection selection (issue #6) and backend constructors (#130 H3).

The ``connect("oda", ...)`` form is deprecated; these tests check it still works.
"""

from __future__ import annotations

import pytest

import sashiny
from sashiny.engines.saspy import ODA_HOSTS, connect, oda, sas94_iom, sas94_ssh, viya

pytestmark = pytest.mark.filterwarnings("ignore:connect\\(profile:DeprecationWarning")


def test_connect_oda_builds_config() -> None:
    engine = connect("oda", region="us1")
    cfg = engine.cfg
    assert cfg["iomhost"] == ODA_HOSTS["us1"]
    assert cfg["iomport"] == 8591
    assert cfg["authkey"] == "oda"
    assert cfg["encoding"] == "utf-8"


def test_connect_oda_unknown_region() -> None:
    with pytest.raises(ValueError, match="unknown ODA region"):
        connect("oda", region="xx9")


def test_connect_viya_requires_url() -> None:
    with pytest.raises(ValueError, match="url is required"):
        connect("viya")


def test_connect_viya_builds_config() -> None:
    engine = connect("viya", url="https://viya.example.com", context="SAS Studio compute context")
    cfg = engine.cfg
    assert cfg["url"] == "https://viya.example.com"
    assert cfg["authkey"] == "viya"
    assert cfg["context"] == "SAS Studio compute context"


def test_connect_sas94_iom_builds_config() -> None:
    engine = connect("sas94", host="sas.example.com", port=8591)
    cfg = engine.cfg
    assert cfg["iomhost"] == "sas.example.com"
    assert cfg["iomport"] == 8591
    assert cfg["authkey"] == "iom"


def test_connect_sas94_ssh_builds_config() -> None:
    engine = connect("sas94", host="sas.example.com", saspath="/opt/sas/sas_u8", ssh_user="me")
    cfg = engine.cfg
    assert cfg["saspath"] == "/opt/sas/sas_u8"
    assert cfg["host"] == "sas.example.com"
    assert cfg["luser"] == "me"


def test_connect_sas94_requires_host() -> None:
    with pytest.raises(ValueError, match="host is required"):
        connect("sas94")


def test_connect_unknown_profile() -> None:
    with pytest.raises(ValueError, match="unknown profile"):
        connect("bogus")


def test_each_profile_maps_to_a_supported_backend() -> None:
    assert connect("oda").backend == "oda"
    assert connect("viya", url="https://v.example.com").backend == "viya"
    assert connect("sas94", host="h.example.com").backend == "sas94-iom"
    assert connect("sas94", host="h.example.com", saspath="/opt/sas").backend == "sas94-ssh"
    assert connect("oda", license_ack=True).license_ack is True


def test_saspy_engine_accepts_only_supported_backends() -> None:
    from sashiny import SaspyEngine  # noqa: PLC0415

    assert SaspyEngine("/path/to/sascfg_personal.py").backend == "cfgfile"
    cases = [
        ({"provider": "sas.iomprovider"}, "COM"),
        ({"saspath": "/opt/sas/sas"}, "STDIO"),
        ({"java": "java"}, "exactly one connection"),
        ({"url": "viya.example.com"}, "https://"),
        ({"url": "https://v", "iomhost": "h"}, "exactly one"),
        ({"iomhost": ["a", "b"]}, "exactly one iomhost"),
    ]
    for cfg, message in cases:
        with pytest.raises(ValueError, match=message):
            SaspyEngine(cfg)
    with pytest.raises(TypeError):
        SaspyEngine({"url": "https://v"}, session_factory=lambda: None)  # type: ignore[call-arg]


def test_env_credentials_become_saspy_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    from sashiny.engines.saspy import env_credentials  # noqa: PLC0415

    monkeypatch.setenv("SASHINY_SAS_USER", "me")
    monkeypatch.setenv("SASHINY_SAS_PASSWORD", "pw")
    assert env_credentials({"iomhost": "h"}) == {"omruser": "me", "omrpw": "pw"}
    assert env_credentials({"url": "https://v"}) == {"user": "me", "pw": "pw"}
    assert env_credentials({"saspath": "/s", "host": "h"}) == {}
    monkeypatch.delenv("SASHINY_SAS_PASSWORD")
    assert env_credentials({"iomhost": "h"}) == {}


def test_constructors_match_the_old_form() -> None:
    assert connect(oda("eu1")).cfg == connect("oda", region="eu1").cfg
    assert (
        connect(viya("https://v.example.com", context="c")).cfg
        == connect("viya", url="https://v.example.com", context="c").cfg
    )
    assert connect(sas94_iom("h.example.com", port=1234)).cfg == (
        connect("sas94", host="h.example.com", port=1234).cfg
    )
    ssh = connect(sas94_ssh("h.example.com", "/opt/sas", ssh_user="me"))
    assert ssh.cfg == connect("sas94", host="h.example.com", saspath="/opt/sas", ssh_user="me").cfg
    assert ssh.backend == "sas94-ssh"
    assert repr(sashiny.oda("ap1")) == "<sashiny backend> oda (ap1)"


def test_constructors_validate_their_own_arguments() -> None:
    with pytest.raises(sashiny.EngineError, match="unknown ODA region"):
        oda("xx9")
    with pytest.raises(ValueError, match="must be one SAS Viya URL"):
        viya("viya.example.com")
    with pytest.raises(ValueError, match="host must be one"):
        sas94_iom("")
    with pytest.raises(ValueError, match="port must be an integer"):
        sas94_iom("h", port=70000)
    with pytest.raises(ValueError, match="saspath must be"):
        sas94_ssh("h", "")
    with pytest.raises(ValueError, match="backend must come from"):
        connect(object())  # type: ignore[arg-type]


@pytest.mark.filterwarnings("default")
def test_old_form_warns() -> None:
    with pytest.warns(DeprecationWarning, match="pass a backend"):
        assert connect("oda").backend == "oda"
