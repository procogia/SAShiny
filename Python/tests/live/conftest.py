"""Live SAS fixtures. Every test here is skipped unless ``SASHINY_LIVE=1``.

Connection (credentials always come from ``~/.authinfo``, never from here).
Running these tests acknowledges the SAS licence for the chosen system.

    SASHINY_PROFILE       oda | viya | sas94           (required)
    SASHINY_ODA_REGION    us1 | us2 | eu1 | ap1 | ap2  (oda; default us1)
    SASHINY_VIYA_URL      https://viya.example.com     (viya)
    SASHINY_VIYA_CONTEXT  compute context name         (viya, optional)
    SASHINY_SAS94_HOST    sas94.example.com            (sas94)
    SASHINY_SAS94_PORT    IOM port                     (sas94, default 8591)
    SASHINY_SAS94_SASPATH SAS executable; uses SSH     (sas94, optional)
    SASHINY_JAVA          Java executable for IOM      (optional)
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

import sashiny

LIVE = os.environ.get("SASHINY_LIVE") == "1"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if LIVE:
        return
    skip = pytest.mark.skip(
        reason="live SAS tests need SASHINY_LIVE=1 (see tests/live/conftest.py)"
    )
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


def _connect() -> sashiny.SaspyEngine:
    env = os.environ
    profile = env.get("SASHINY_PROFILE", "")
    java = env.get("SASHINY_JAVA")
    if profile == "oda":
        return sashiny.connect(
            sashiny.oda(env.get("SASHINY_ODA_REGION", "us1"), java=java), license_ack=True
        )
    if profile == "viya":
        return sashiny.connect(
            sashiny.viya(env.get("SASHINY_VIYA_URL", ""), context=env.get("SASHINY_VIYA_CONTEXT")),
            license_ack=True,
        )
    if profile == "sas94":
        host = env.get("SASHINY_SAS94_HOST", "")
        saspath = env.get("SASHINY_SAS94_SASPATH")
        backend = (
            sashiny.sas94_ssh(host, saspath)
            if saspath
            else sashiny.sas94_iom(host, port=int(env.get("SASHINY_SAS94_PORT", "8591")), java=java)
        )
        return sashiny.connect(backend, license_ack=True)
    raise pytest.UsageError("SASHINY_PROFILE must be oda, viya or sas94")


@pytest.fixture(scope="session")
def live_engine() -> Iterator[sashiny.SaspyEngine]:
    """One live SAS session for the whole run (closed at the end)."""
    engine = _connect()
    yield engine
    engine.close()


@pytest.fixture(scope="session")
def scratch_engine() -> Iterator[sashiny.SaspyEngine]:
    """A second, independent live session."""
    engine = _connect()
    yield engine
    engine.close()
