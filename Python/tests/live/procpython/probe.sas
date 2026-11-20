/* SAShiny PROC PYTHON probe (#128 step 1 and live parity). Run by QA only.
   Prerequisites: PROC PYTHON enabled (lockdown enable_ams=PYTHON;), the sashiny
   package installed in the configured Python, and this repository readable
   from the compute server. Set the two paths below, then submit the whole file.
   Submitting it acknowledges the SAS licence for this system. */
%let repo=/path/to/SAShiny;
%let out=%sysfunc(pathname(work));

proc python;
submit;
import json, pathlib, sys
repo = pathlib.Path(SAS.symget("repo"))
out = pathlib.Path(SAS.symget("out"))
report = {}

# 1. What does SAS.submit return?
ret = SAS.submit("%put NOTE: SASHINY-PROBE;")
report["submit_returns"] = repr(type(ret)) + " " + repr(ret)[:200]

# 2. Is the WORK path readable from Python?
work = pathlib.Path(SAS.workpath()) if hasattr(SAS, "workpath") else None
report["workpath"] = str(work)
report["work_readable"] = bool(work and work.is_dir())

# 3. Does sashiny import?
try:
    import sashiny
    report["sashiny"] = sashiny.__version__
except Exception as exc:
    report["sashiny"] = f"import failed: {exc}"

# 4. Do PRINTTO and ODS HTML5 capture work, and does a contract run?
if not report["sashiny"].startswith("import failed"):
    eng = sashiny.connect_in_session(SAS, license_ack=True, own_session=True)
    for name in ["minimal", "outputs"]:
        path = repo / "spec" / "fixtures" / "contracts" / "valid" / name / "contract.sashiny.yml"
        res = sashiny.run(path, eng, {})
        report[name] = {"status": res.status, "log_chars": len(res.log),
                        "outputs": sorted(res.outputs), "error": res.metadata.get("engine_error")}
        (out / f"sashiny_parity_{name}.json").write_text(json.dumps(res.outputs, default=str))

(out / "sashiny_probe.json").write_text(json.dumps(report, indent=2, default=str))
print(json.dumps(report, indent=2, default=str))
endsubmit;
run;