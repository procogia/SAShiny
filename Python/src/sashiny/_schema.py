"""Bundled JSON Schema for the SAShiny sidecar contract.

The schema is a copy of ``spec/sashiny.schema.json``, synced into the package
at build time so the library is self-contained (no dependency on the repo's
``spec/`` directory at runtime).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parent / "_data" / "sashiny.schema.json"

SCHEMA: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))

__all__ = ["SCHEMA"]
