"""Expose SAShiny operations without replacing their validation or error semantics."""
from __future__ import annotations

import base64
import dataclasses
import importlib.metadata
import io
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path

import sashiny
from sashiny import collect
from sashiny.contract import all_macro_names, macro_names
from sashiny.engines.saspy import classify_log, run_status
from sashiny.recording import key_for
from sashiny.upload import UploadFile, read_upload, sanitize_names

REPO = Path("/tmp/SAShiny")
sys.path.insert(0, str(REPO / "Python" / "tests"))
TODAY = date(2026, 11, 11)


def frame_value(frame):
    import pandas as pd
    rows = []
    for row in frame.itertuples(index=False, name=None):
        rows.append([None if pd.isna(c) else c.isoformat() if hasattr(c, "isoformat")
                     else c.item() if hasattr(c, "item") else c for c in row])
    return {"columns": list(frame.columns), "dtypes": [str(d) for d in frame.dtypes], "rows": rows}


def fixture_uploads(p):
    return {iid: UploadFile(Path(p["folder"]) / v, Path(v).name) if isinstance(v, str)
            else v for iid, v in p.get("uploads", {}).items()}


def pool_case(p, contract):
    from sashiny.pool import Pool
    name = p.get("scenario", "reuse")
    counts = {"created": 0, "closed": 0, "runs": 0, "active": 0, "peak": 0}
    lock = threading.Lock()
    def factory():
        with lock:
            counts["created"] += 1
        class TestEngine(sashiny.Engine):
            def run(self, contract, values, **kwargs):
                with lock:
                    counts["runs"] += 1
                    counts["active"] += 1
                    counts["peak"] = max(counts["peak"], counts["active"])
                time.sleep(p.get("delay", 0))
                with lock:
                    counts["active"] -= 1
                if name == "raised_engine":
                    raise RuntimeError("synthetic transport failure")
                if name == "validation":
                    r = sashiny.Result.new("audit", "error")
                    r.metadata["issues"] = [{"code": "V001", "input": "x"}]
                    return r
                return sashiny.Result.new("audit", "error" if name == "error" else "success")
            def choices(self, contract):
                if name == "choices_error":
                    raise RuntimeError("synthetic choices failure")
                return {"x": [{"value": "a", "label": "A"}]}
            def close(self):
                counts["closed"] += 1
                if name == "close_error":
                    raise RuntimeError("synthetic close failure")
        if name == "factory_error":
            raise RuntimeError("synthetic factory failure")
        return TestEngine()
    config = {"max_size": 2, "acquire_timeout": 0.15, **p.get("config", {})}
    if name == "shared_engine":
        pool = Pool(factory(), **config)
    else:
        pool = Pool(factory, **config)
    results, errors = [], []
    held = None
    try:
        if name == "busy_choices":
            held = pool._acquire()
            try:
                results.append(pool.choices(contract))
            except Exception as exc:
                errors.append(str(exc))
        elif name == "choices_error":
            try:
                pool.choices(contract)
            except Exception as exc:
                errors.append(str(exc))
        elif name == "close_reopen":
            pool.run(contract, {})
            pool.close()
            results.append(dataclasses.asdict(pool.run(contract, {})))
        elif name == "close_inflight":
            worker = threading.Thread(target=lambda: results.append(
                dataclasses.asdict(pool.run(contract, {}))))
            worker.start()
            deadline = time.monotonic()+2
            while not counts["active"] and time.monotonic()<deadline:
                time.sleep(0.001)
            pool.close()
            worker.join(3)
            if worker.is_alive():
                raise RuntimeError("audit worker failed to settle")
        elif name == "idle":
            pool.run(contract, {})
            time.sleep(0.03)
            results.append(dataclasses.asdict(pool.run(contract, {})))
        elif name in ("parallel", "timeout", "shared_engine"):
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [executor.submit(pool.run, contract, {}) for _ in range(4)]
                for f in futures:
                    try:
                        results.append(dataclasses.asdict(f.result(timeout=6)))
                    except Exception as exc:
                        errors.append(str(exc))
        else:
            for _ in range(p.get("runs", 2)):
                results.append(dataclasses.asdict(pool.run(contract, {})))
        before_close = len(pool._sessions)
    finally:
        if held is not None:
            pool._release(held, False)
        try:
            pool.close()
        except Exception as exc:
            errors.append(str(exc))
    return {"counts": counts, "results": results, "errors": errors,
            "sessions_before_close": before_close, "sessions_after_close": len(pool._sessions)}


def fake_case(p, contract):
    from fakesas import FakeSAS
    import pandas as pd
    frames = {tuple(name.upper().split(".", 1)): pd.DataFrame(v["rows"], columns=v["columns"])
              for name, v in p.get("datasets", {}).items()}
    options = {k: p[k] for k in ("syscc", "program_log", "lst") if k in p}
    files = {name: base64.b64decode(value) for name, value in p.get("remote_files", {}).items()}
    sessions, lifecycle = [], []
    scenario = p.get("scenario", "")
    def factory():
        if scenario == "slow_factory":
            time.sleep(1.5)
        fake = FakeSAS(frames, files=files, **options)
        original = fake.submit
        def submit(code, results="HTML"):
            if scenario == "slow_submit" and "wrapper" in code:
                time.sleep(1.5)
            if scenario == "raise_submit" and "wrapper" in code:
                raise RuntimeError("synthetic submission failure")
            return original(code, results)
        fake.submit = submit
        sessions.append(fake)
        lifecycle.append({"event": "created", "time": time.monotonic()})
        return fake
    rec = Path(p["folder"]) / "rec" if p.get("record") else None
    engine = sashiny.SaspyEngine({}, session_factory=factory, record_to=rec)
    out = []
    for _ in range(p.get("runs", 1)):
        r = engine.run(contract, p.get("values", {}), today=TODAY,
                       uploads=fixture_uploads(p), run_id=p.get("run_id", "audit"))
        out.append(dataclasses.asdict(r))
    if scenario.startswith("slow_"):
        time.sleep(0.75)
    closed_before = [f.ended for f in sessions]
    engine.close()
    return {"results": out, "sessions": len(sessions), "closed_before": closed_before,
            "closed_after": [f.ended for f in sessions],
            "submitted": [s for f in sessions for s in f.submitted],
            "uploaded": {f"{lib}.{mem}": frame_value(frame)
                         for f in sessions for (lib, mem), (frame, _) in f.uploaded.items()},
            "recordings": [path.read_text() for path in rec.glob("*.json")] if rec else []}


def cache_after_failure(p, contract):
    from fakesas import FakeSAS
    import pandas as pd
    made = []
    def factory():
        index = len(made)
        f = FakeSAS({("WORK","CHOICES"):pd.DataFrame({"value":["old" if index==0 else "new"]})})
        submit = f.submit
        def fail_once(code, results="HTML"):
            if index==0 and "wrapper" in code:
                raise RuntimeError("synthetic lost session")
            return submit(code,results)
        f.submit = fail_once
        made.append(f)
        return f
    e = sashiny.SaspyEngine({},session_factory=factory)
    try:
        first = e.choices(contract)
        result = e.run(contract,{"pick":"old"})
        second = e.choices(contract)
        return {"first":first,"failed":dataclasses.asdict(result),"second":second,
                "sessions":len(made),"ended":[f.ended for f in made]}
    finally:
        e.close()


def generation_case(p, contract):
    from fakesas import FakeSAS
    released = threading.Event()
    made = []
    def factory():
        f = FakeSAS()
        index = len(made)
        original = f.submit
        def submit(code, results="HTML"):
            if index==0 and "wrapper" in code:
                released.wait(3)
            return original(code,results)
        f.submit = submit
        made.append(f)
        return f
    engine = sashiny.SaspyEngine({},session_factory=factory)
    try:
        old = engine.run(contract,{},run_id="old")
        new = engine.run(contract,{},run_id="new")
        engine.close()
        released.set()
        deadline = time.monotonic()+1
        while any(t.name=="sashiny-run-old" for t in threading.enumerate()) and time.monotonic()<deadline:
            time.sleep(0.01)
        return {"old":dataclasses.asdict(old),"new":dataclasses.asdict(new),
                "sessions_created":len(made),"closed_before_cleanup":[s.ended for s in made],
                "submissions":[s.submitted for s in made]}
    finally:
        released.set()
        engine.close()


def dispatch(p):
    op = p["operation"]
    if op == "inventory":
        names = ["sashiny", "shiny", "saspy", "jsonschema", "PyYAML", "pandas",
                 "openpyxl", "pyreadstat", "plotnine", "matplotlib", "plotly", "fastapi"]
        return {"python": sys.version, "installed_path": sashiny.__file__,
                "exports": sashiny.__all__,
                "versions": {n: importlib.metadata.version(n) for n in names},
                "backends": sashiny.chart_backends()}
    if op == "module_id":
        return [sashiny.default_module_id(s) for s in p["names"]]
    if op == "profiles":
        if "yaml" in p:
            path = Path(p["folder"]) / "profiles.yml"
            path.write_text(p["yaml"], encoding="utf-8")
        else:
            path = Path(p["folder"]) / "missing-profiles.yml"
        return sashiny.load_profiles(path)
    if op == "connect":
        engine = sashiny.connect(**p["kwargs"])
        config = engine.cfg
        engine.close()
        return config
    if op == "preflight":
        from sashiny.engines.saspy import preflight
        preflight(p["config"])
        return {"passed": True}
    if op == "status":
        status, syscc = run_status(p["log"], p.get("run_id", "audit"))
        return {"status": status, "syscc": syscc, "counts": classify_log(p["log"])}
    if op == "collect":
        name = p["function"]
        functions = {n: getattr(collect, n) for n in collect.__all__ if callable(getattr(collect,n))}
        args = p.get("args", [])
        value = functions[name](*args, **p.get("kwargs", {}))
        return {"base64": base64.b64encode(value).decode()} if isinstance(value, bytes) else value
    if op == "upload":
        result, dates = read_upload(UploadFile(Path(p["folder"]) / p["name"], p["name"]), p["spec"])
        return {**frame_value(result), "datetimes": dates}
    if op == "sanitize":
        return sanitize_names(p["names"])
    if op == "make_upload":
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.append(p["columns"])
        for row in p["rows"]:
            sheet.append([date.fromisoformat(v["date"]) if isinstance(v,dict) and "date" in v
                          else v for v in row])
        path = Path(p["folder"])/"generated.xlsx"
        book.save(path)
        return {"base64":base64.b64encode(path.read_bytes()).decode()}
    if op == "chart":
        from sashiny.modules import chart_tag, _plot_to_png
        spec, backend = p.get("spec"), p.get("backend", "plotnine")
        if p.get("callback"):
            return {"callback": sashiny.render_chart(p["value"], spec, backend,
                                                     render=lambda value, spec: "audit callback")}
        obj = sashiny.render_chart(p["value"], spec, backend)
        if backend == "plotly":
            raw = json.loads(obj.to_json())
            return {"backend": backend, "plot": raw, "html": str(chart_tag(p["value"],
                    {"type": "chart", "spec": {**spec, "backend": backend}})) if p.get("tag") else ""}
        png = _plot_to_png(obj)
        observed = {"backend": backend, "png": png}
        if backend == "matplotlib":
            observed.update(axes=len(obj.axes),
                            lines=len(obj.axes[0].lines),
                            collections=len(obj.axes[0].collections))
        return observed
    contract = sashiny.load(p["contract_path"])
    today = date.fromisoformat(p.get("today", TODAY.isoformat()))
    if op == "validate":
        return {"issues": [dataclasses.asdict(i) for i in sashiny.validate(contract, today)],
                "data": contract.data}
    if op == "values":
        macros, issues = sashiny.render_values(contract.data, p.get("values", {}), today,
             choices_override=p.get("choices"), uploads=p.get("uploads"), only=p.get("only"))
        return {"macros": macros, "macro_order": list(macros),
                "issues": [dataclasses.asdict(i) for i in issues]}
    if op == "macro_names":
        return all_macro_names(contract.data)
    if op == "wrapper":
        program = (contract.base_dir / contract.data["program"]).read_bytes()
        macros, issues = sashiny.render_values(contract.data,p.get("values",{}),today,
                                               uploads=p.get("uploads"))
        return {"issues": [dataclasses.asdict(i) for i in issues],
                "main": sashiny.wrapper_code(contract.data, macros, program,
                                             p.get("run_id","fixture")),
                "reset": sashiny.reset_code(contract.data),
                "program_b64": base64.b64encode(program).decode()}
    if op == "lint":
        text = (contract.base_dir / contract.data["program"]).read_text(encoding="utf-8")
        return [dataclasses.asdict(i) for i in sashiny.lint(contract.data, text)]
    if op in ("mock", "runner"):
        engine = sashiny.MockEngine(Path(p["folder"]) / "rec", choices=p.get("choices"))
        uploads = fixture_uploads(p)
        if "recording" in p:
            macros, issues = sashiny.render_values(contract.data,p.get("values",{}),today,
                                                   uploads={k: bool(v) for k,v in uploads.items()})
            engine.save_recording(contract, macros, p["recording"],
                                  {k:v.path for k,v in uploads.items() if isinstance(v,UploadFile)})
        fn = engine.run if op == "mock" else lambda c,v,**kw: sashiny.run(c,v,engine,**kw)
        r = fn(contract if not p.get("by_path") else p["contract_path"],
               p.get("values",{}),today=today,uploads=uploads,run_id=p.get("run_id","audit"))
        engine.close()
        return dataclasses.asdict(r)
    if op == "recording":
        engine = sashiny.MockEngine(Path(p["folder"]) / "rec")
        engine.save_recording(contract,p.get("macros",{}),p["recording"])
        key = key_for(contract,p.get("macros",{}),{})
        from sashiny.recording import load_recording, save_recording
        original = load_recording(engine.recordings_dir, key)
        result = sashiny.Result.new("audit","success")
        result.outputs = p["recording"].get("outputs",{})
        second = save_recording(engine.recordings_dir,"second",result)
        return {"key": key, "raw": (engine.recordings_dir/f"{key}.json").read_text(),
                "loaded": original, "result_raw": second.read_text()}
    if op == "fake":
        return fake_case(p, contract)
    if op == "choices_cache":
        return cache_after_failure(p, contract)
    if op == "generation_cancel":
        return generation_case(p, contract)
    if op == "raw_replay":
        rec = Path(p["folder"])/"rec"
        rec.mkdir()
        macros, _ = sashiny.render_values(contract.data,p.get("values",{}),today)
        key = key_for(contract,macros,{})
        (rec/f"{key}.json").write_text(p["raw"],encoding="utf-8")
        return dataclasses.asdict(sashiny.MockEngine(rec).run(contract,p.get("values",{}),today=today))
    if op == "pool":
        return pool_case(p, contract)
    if op == "ui":
        from sashiny import modules
        ui = modules.program_ui("mod",contract,today=today,
                ui_override=(lambda c: "audit override") if p.get("override") else None)
        return {"html": str(ui)}
    if op == "shiny_values":
        from sashiny.modules import shiny_values
        vals, uploads = shiny_values(contract, lambda iid:p.get("raw",{}).get(iid))
        return {"values": vals, "uploads": {k:dataclasses.asdict(v) if isinstance(v,UploadFile)
                                           else v for k,v in uploads.items()}}
    if op == "app":
        import copy
        other = copy.deepcopy(contract)
        if "other_id" in p:
            other.data["id"] = p["other_id"]
        app = sashiny.app([contract,other] if p.get("duplicate") else [contract], sashiny.MockEngine())
        return {"built": True, "type": type(app).__name__}
    raise ValueError(f"unsupported audit operation: {op}")
