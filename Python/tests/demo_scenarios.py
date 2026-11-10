"""Demo scenarios (``examples/demo-scenarios.yml``) and the result checker.

Used by the offline scenario tests and the live SAS suite. ``check_result``
returns a list of problems (empty means the run is demo-ready), so a failing
test reports every problem at once.
"""

from __future__ import annotations

import base64
import csv
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

import sashiny

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = REPO / "examples"
SCENARIOS_FILE = EXAMPLES / "demo-scenarios.yml"
RECORDINGS = EXAMPLES / "recordings"

# Leading bytes of each download format.
MAGIC = {
    "pdf": b"%PDF-",
    "rtf": b"{\\rtf",
    "xlsx": b"PK\x03\x04",
    "xpt": b"HEADER RECORD*******LIBRARY HEADER RECORD",
    "sas7bdat": bytes(12) + bytes.fromhex("c2ea8160b31411cfbd92080009c7318c181f1011"),
}
MIME_PREFIX = ("image/png", "image/svg+xml", "image/jpeg", "image/gif")


@dataclass(frozen=True)
class Scenario:
    """One demo run: a contract, its inputs and what the run must produce."""

    id: str
    title: str
    contract_path: Path
    primary: bool
    values: dict[str, Any]
    upload_ids: tuple[str, ...]
    expect: dict[str, Any]

    @property
    def uploads(self) -> dict[str, Any]:
        """The ``uploads=`` argument: ``True`` selects each input's sample file."""
        return dict.fromkeys(self.upload_ids, True)

    def load(self) -> sashiny.Contract:
        """Load the scenario's contract."""
        return sashiny.load(self.contract_path)


def load_scenarios() -> list[Scenario]:
    """Read every scenario from ``examples/demo-scenarios.yml``."""
    data = yaml.safe_load(SCENARIOS_FILE.read_text(encoding="utf-8"))
    out = []
    for s in data["scenarios"]:
        for iid, how in (s.get("uploads") or {}).items():
            if how != "sample":
                raise ValueError(f"{s['id']}: upload {iid} must be 'sample'")
        out.append(
            Scenario(
                id=s["id"],
                title=s["title"],
                contract_path=EXAMPLES / s["contract"],
                primary=bool(s.get("primary", False)),
                values=s.get("values") or {},
                upload_ids=tuple((s.get("uploads") or {}).keys()),
                expect=s.get("expect") or {},
            )
        )
    return out


def default_problems(scenario: Scenario, contract: sashiny.Contract) -> list[str]:
    """Differences between a primary scenario and what the untouched UI sends."""
    problems = []
    for iid, spec in (contract.data.get("inputs") or {}).items():
        if spec["type"] == "dataset":
            if "sample" in spec and iid not in scenario.upload_ids:
                problems.append(
                    f"{iid}: the UI ticks 'Use the sample file' but the scenario does not"
                )
            continue
        if "default" in spec and scenario.values.get(iid) != spec["default"]:
            problems.append(
                f"{iid}: scenario value {scenario.values.get(iid)!r}"
                f" != contract default {spec['default']!r}"
            )
    return problems


def _download_problems(
    oid: str, fmt: str, value: dict[str, Any], contract: sashiny.Contract
) -> list[str]:
    spec = contract.data["outputs"][oid]
    expected_name = f"{spec.get('filename', oid)}.{fmt}"
    problems = []
    if value.get("filename") != expected_name:
        problems.append(f"{oid}: filename {value.get('filename')!r} != {expected_name!r}")
    try:
        data = base64.b64decode(value["data"], validate=True)
    except (KeyError, ValueError) as exc:
        return [*problems, f"{oid}: download data is not base64 ({exc})"]
    if not data:
        return [*problems, f"{oid}: download is empty"]
    if fmt == "csv":
        rows = list(csv.reader(io.StringIO(data.decode("utf-8"))))
        if len(rows) < 2:
            problems.append(f"{oid}: CSV has no data rows")
    elif not data.startswith(MAGIC[fmt]):
        problems.append(f"{oid}: not a valid .{fmt} file (starts with {data[:16]!r})")
    return problems


def check_result(  # noqa: PLR0912 - one branch per kind of problem
    result: sashiny.Result, contract: sashiny.Contract, scenario: Scenario
) -> list[str]:
    """Return every reason the result is not demo-ready (empty list = ready)."""
    expect = scenario.expect
    problems = []
    if result.status != expect.get("status", "success"):
        problems.append(f"status {result.status!r} != {expect.get('status', 'success')!r}")
    meta = result.metadata
    for key in ("issues", "engine_error"):
        if meta.get(key):
            problems.append(f"{key}: {meta[key]}")
    problems += [f"collect error: {e}" for e in meta.get("collect_errors", [])]
    for oid, spec in contract.data["outputs"].items():
        value = result.outputs.get(oid)
        if value is None:
            problems.append(f"{oid}: missing from outputs")
            continue
        if isinstance(value, dict) and "error" in value:
            problems.append(f"{oid}: {value['error']}")
            continue
        kind = spec["type"]
        if kind == "table":
            minimum = (expect.get("tables") or {}).get(oid, {}).get("min_rows", 0)
            if len(value["rows"]) < minimum:
                problems.append(f"{oid}: {len(value['rows'])} rows, expected at least {minimum}")
            if not value["columns"]:
                problems.append(f"{oid}: no columns")
        elif kind == "plot":
            minimum = (expect.get("plots") or {}).get(oid, 0)
            if len(value) < minimum:
                problems.append(f"{oid}: {len(value)} graphs, expected at least {minimum}")
            problems += [
                f"{oid}: unexpected mime {p['mime']}" for p in value if p["mime"] not in MIME_PREFIX
            ]
        elif kind == "html":
            if "<html" not in value.lower():
                problems.append(f"{oid}: not an HTML document")
        elif kind == "log":
            errors = [line["text"] for line in value if line["level"] == "error"]
            problems += [f"{oid}: SAS log error: {text}" for text in errors]
            if not value:
                problems.append(f"{oid}: program log is empty")
        elif kind == "download":
            problems += _download_problems(oid, spec["format"], value, contract)
    return problems
