"""Live session-reuse timing check (#130 J1/J2). Skipped unless ``SASHINY_LIVE=1``.

Runs ``examples/general/cars_explorer.sashiny.yml`` 10 times on one engine and
10 times on a pool of two. For each run it records the wall time and the SAS
process id. The id comes from a test-only probe program that does
``%put SXPID=&sysjobid;`` and then ``%include``s the unchanged example
program. Neither the user program nor the production wrapper changes.

It writes a CSV report to the temp folder and prints a summary: distinct process
ids, median and p90 run time.

Run it from ``Python/``:

    SASHINY_LIVE=1 SASHINY_PROFILE=oda uv run --extra saspy \
        pytest tests/live/test_live_session_reuse.py -s
"""

from __future__ import annotations

import csv
import re
import statistics
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import yaml

import sashiny
from _repo import repo_root

pytestmark = pytest.mark.live

RUNS = 10
EXAMPLE = repo_root() / "examples" / "general"
_PID = re.compile(r"^SXPID=(\S+)", re.MULTILINE)


def _probe_contract(folder: Path) -> sashiny.Contract:
    """Copy the example and point its contract at a probe program (test only)."""
    # The probe inlines the example's text after the %put, so no remote file path
    # is needed (the SAS server cannot see this machine's temp folder).
    program = (EXAMPLE / "cars_explorer.sas").read_text(encoding="utf-8")
    (folder / "probe.sas").write_text("%put SXPID=&sysjobid;\n" + program, encoding="utf-8")
    data = yaml.safe_load((EXAMPLE / "cars_explorer.sashiny.yml").read_text(encoding="utf-8"))
    data["program"] = "probe.sas"
    data.setdefault("inputs", {})
    path = folder / "probe.sashiny.yml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return sashiny.load(path)


def _pid(result: sashiny.Result) -> str:
    m = _PID.search(result.log)
    return m.group(1) if m else ""


def _series(engine: sashiny.Engine, contract: sashiny.Contract) -> list[tuple[float, str]]:
    out = []
    for _ in range(RUNS):
        t0 = time.perf_counter()
        result = engine.run(contract, {}, today=date.today())
        out.append((time.perf_counter() - t0, _pid(result)))
        assert result.status in ("success", "warning"), result.metadata.get("engine_error")
    return out


def _summary(label: str, rows: list[tuple[float, str]]) -> str:
    times = sorted(t for t, _ in rows)
    p90 = times[max(0, round(0.9 * len(times)) - 1)]
    pids = {p for _, p in rows}
    return (
        f"{label}: {len(pids)} distinct SAS process id(s); "
        f"median {statistics.median(times):.2f} s, p90 {p90:.2f} s"
    )


def test_one_engine_reuses_its_sas_session(live_engine: sashiny.SaspyEngine) -> None:
    folder = Path(tempfile.mkdtemp(prefix="sashiny-reuse-"))
    contract = _probe_contract(folder)
    single = _series(live_engine, contract)
    pool = sashiny.Pool(sashiny.connect_from_env, max_size=2)
    try:
        pooled = _series(pool, contract)
    finally:
        pool.close()
    report = folder / "session-reuse-python.csv"
    with report.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "run", "seconds", "sas_pid", "recorded_at"])
        stamp = datetime.now(timezone.utc).isoformat()
        for mode, rows in (("engine", single), ("pool2", pooled)):
            for i, (secs, pid) in enumerate(rows, 1):
                w.writerow([mode, i, f"{secs:.3f}", pid, stamp])
    print(
        f"\n{_summary('engine', single)}\n{_summary('pool(max_size=2)', pooled)}\nreport: {report}"
    )
    assert all(p for _, p in single), "SXPID missing from the log"
    assert len({p for _, p in single}) == 1, "one engine must reuse one SAS session (spec 6.5)"
    assert len({p for _, p in pooled}) <= 2, "a pool of 2 must use at most 2 SAS sessions"
