"""Tests for the SAS connection selection (issue #6)."""

from __future__ import annotations

import pytest

from sashiny.engines.saspy import ODA_HOSTS, connect


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
