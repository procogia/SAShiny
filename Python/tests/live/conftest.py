"""Live SAS fixtures. Every test here is skipped unless ``SASHINY_LIVE=1``.

Connection (credentials always come from ``~/.authinfo``, never from here):

    SASHINY_PROFILE       oda | viya | sas94           (required)
    SASHINY_ODA_REGION    us1 | us2 | eu1 | ap1 | ap2  (oda; default us1)
    SASHINY_VIYA_URL      https://viya.example.com     (viya)
    SASHINY_VIYA_CONTEXT  compute context name         (viya, optional)
    SASHINY_SAS94_HOST    sas94.example.com            (sas94)
    SASHINY_SAS94_PORT    IOM port                     (sas94, default 8591)
    SASHINY_SAS94_SASPATH SAS executable; uses SSH     (sas94, optional)
    SASHINY_JAVA          Java executable for IOM      (optional)
    SASHINY_RECORD_TO     directory for recordings     (default: a temp dir;
                          use examples/recordings to fill the demo fallback)
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

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


def _connect(record_to: Path) -> sashiny.SaspyEngine:
    env = os.environ
    profile = env.get("SASHINY_PROFILE", "")
    java = env.get("SASHINY_JAVA")
    if profile == "oda":
        return sashiny.connect(
            "oda", region=env.get("SASHINY_ODA_REGION", "us1"), java=java, record_to=record_to
        )
    if profile == "viya":
        return sashiny.connect(
            "viya",
            url=env.get("SASHINY_VIYA_URL"),
            context=env.get("SASHINY_VIYA_CONTEXT"),
            record_to=record_to,
        )
    if profile == "sas94":
        return sashiny.connect(
            "sas94",
            host=env.get("SASHINY_SAS94_HOST"),
            port=int(env.get("SASHINY_SAS94_PORT", "8591")),
            saspath=env.get("SASHINY_SAS94_SASPATH"),
            java=java,
            record_to=record_to,
        )
    raise pytest.UsageError("SASHINY_PROFILE must be oda, viya or sas94")


@pytest.fixture(scope="session")
def record_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Where live runs are recorded."""
    configured = os.environ.get("SASHINY_RECORD_TO")
    return Path(configured) if configured else tmp_path_factory.mktemp("recordings")


@pytest.fixture(scope="session")
def live_engine(record_dir: Path) -> Iterator[sashiny.SaspyEngine]:
    """One live SAS session for the whole run (closed at the end)."""
    engine = _connect(record_dir)
    yield engine
    engine.close()


@pytest.fixture(scope="session")
def scratch_engine(tmp_path_factory: pytest.TempPathFactory) -> Iterator[sashiny.SaspyEngine]:
    """A second live session whose runs are not recorded."""
    engine = _connect(tmp_path_factory.mktemp("scratch"))
    engine.record_to = None
    yield engine
    engine.close()
