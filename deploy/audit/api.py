"""Disposable audit API: fixed operations only, synthetic data, no live SAS."""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response

ROOT = Path("/tmp/audit")
REPO = Path("/tmp/SAShiny")
# The revision under test. In Docker this is the checked-out HEAD; the original
# Daytona audit pinned dd0bf60. Override with SASHINY_AUDIT_SHA if needed.
SHA = os.environ.get("SASHINY_AUDIT_SHA", "3ad76f72b7ee6169830e97226eb59492ec795c1a")
ROOT.joinpath("work").mkdir(parents=True, exist_ok=True)
R_LOCK = threading.Lock()
app = FastAPI(title="SAShiny synthetic audit API", version=SHA[:7])


def stage(request: dict, folder: Path) -> dict:
    request = dict(request)
    relative = request.get("fixture")
    if relative:
        path = (REPO / "spec" / "fixtures" / relative / "contract.sashiny.yml").resolve()
        if not path.is_relative_to(REPO / "spec" / "fixtures"):
            raise HTTPException(400, "fixture path outside fixture root")
    elif request.get("example"):
        path = (REPO / "examples" / request["example"]).resolve()
        if not path.is_relative_to(REPO / "examples"):
            raise HTTPException(400, "example path outside examples root")
    else:
        path = folder / "contract.sashiny.yml"
        text = request.get("yaml")
        if text is None:
            data = request.get("data", {
                "sashiny": 1, "program": "program.sas", "title": "Audit",
                "outputs": {"report": {"type": "log"}},
            })
            text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
        path.write_text(text, encoding="utf-8")
        program = folder / request.get("program_name", "program.sas")
        if not program.resolve().is_relative_to(folder):
            raise HTTPException(400, "program path outside work directory")
        if not request.get("missing_program"):
            program.parent.mkdir(parents=True, exist_ok=True)
            program.write_bytes(base64.b64decode(request["program_b64"]) if "program_b64" in request
                                else request.get("program", "data work.out; run;\n").encode())
    request["contract_path"] = str(path)
    request["folder"] = str(folder)
    for item in request.get("files", []):
        dest = folder / item["name"]
        if not dest.resolve().is_relative_to(folder):
            raise HTTPException(400, "upload path outside work directory")
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not item.get("missing"):
            if "base64" in item:
                dest.write_bytes(base64.b64decode(item["base64"]))
            else:
                dest.write_text(item.get("text", ""), encoding="utf-8")
    return request


@app.get("/health")
def health() -> dict:
    return {"sha": SHA, "role": "server", "hostname": os.uname().nodename,
            "sas_backend": "fake/mock only", "time": time.time()}


@app.post("/invoke/{language}/{operation}")
def invoke(language: str, operation: str, body: dict) -> Response:
    if language not in ("python", "r"):
        raise HTTPException(400, "language must be python or r")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="request-", dir=ROOT / "work") as tmp:
        request = stage(body, Path(tmp))
        request["operation"] = operation
        try:
            if language == "python":
                from ops_py import dispatch
                payload = {"ok": True, "value": dispatch(request)}
            else:
                p = Path(tmp) / "request.json"
                p.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
                with R_LOCK:
                    run = subprocess.run(
                        ["Rscript", "--vanilla", str(ROOT / "ops_r.R"), str(p)],
                        cwd="/tmp", text=True, encoding="utf-8",
                        capture_output=True, timeout=45,
                    )
                lines = [s[13:] for s in run.stdout.splitlines() if s.startswith("AUDIT_RESULT=")]
                if run.returncode or len(lines) != 1:
                    payload = {"ok": False, "harness_error": True, "exit_code": run.returncode,
                               "stdout": run.stdout[-4000:], "stderr": run.stderr[-4000:]}
                else:
                    payload = json.loads(lines[0])
                    if run.stderr:
                        payload["stderr"] = run.stderr[-3000:]
        except Exception as exc:
            payload = {"ok": False, "exception": type(exc).__name__, "message": str(exc),
                       "traceback": traceback.format_exc()[-5000:]}
        payload.update(language=language, operation=operation, seconds=time.monotonic()-started)
        with (ROOT / "results" / "requests.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"case_id": body.get("case_id"), **payload}, default=str) + "\n")
        return Response(json.dumps(payload, default=str, ensure_ascii=False),
                        media_type="application/json")


@app.get("/spy-events/{language}")
def spy_events(language: str) -> list:
    if language not in ("python", "r"):
        raise HTTPException(400)
    path = ROOT / f"{language}-events.jsonl"
    return [json.loads(s) for s in path.read_text().splitlines()] if path.is_file() else []


@app.get("/bundle")
def bundle() -> FileResponse:
    archive = shutil.make_archive(str(ROOT / "export"), "zip", ROOT, "results")
    return FileResponse(archive, media_type="application/zip")


@app.get("/coverage")
def coverage_dump() -> dict:
    import coverage
    current = coverage.Coverage.current()
    if current is None:
        return {"enabled": False}
    current.save()
    current.json_report(outfile=str(ROOT / "results" / "api-coverage.json"))
    report = json.loads((ROOT / "results" / "api-coverage.json").read_text())
    return {"enabled": True, "totals": report["totals"]}
