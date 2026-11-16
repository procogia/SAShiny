"""Engine helpers for the test suite.

PyPI and CI checks have no SAS, so the tests use two internal fixtures: the
offline mock engine (``sashiny.engines._mock.MockEngine``) and a saspy engine
backed by a fake session (``fakesas.py``). Neither one can be reached through
the public API (spec §6.6).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sashiny import Contract, Result, SaspyEngine
from sashiny.engines._mock import MockEngine
from sashiny.recording import key_for

__all__ = ["MockEngine", "fake_engine", "save_recording"]


def fake_engine(
    factory: Callable[[], Any], cfg: dict[str, Any] | None = None, *, license_ack: bool = True
) -> SaspyEngine:
    """A saspy engine on a fake session, licence acknowledged."""
    engine = SaspyEngine(cfg or {"iomhost": "sas.test", "java": "java"}, license_ack=license_ack)
    engine._factory = factory
    return engine


def save_recording(
    directory: Path, contract: Contract, result: Result, files: dict[str, Path] | None = None
) -> Path:
    """Save a run result as a recording (§8.3) for the mock engine to replay."""
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "sashiny_recording": 1,
        "status": result.status,
        "log": result.log,
        "outputs": result.outputs,
        "sas_version": result.metadata.get("sas_version", ""),
        "macros": result.metadata.get("macros", {}),
        "recorded_at": "2026-11-11T00:00:00+00:00",
    }
    path = directory / f"{key_for(contract, result.metadata.get('macros', {}), files or {})}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
