"""Build the final evidence index; verdicts are manually adjudicated, not inferred."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parent
manifest=json.loads((ROOT/"manifest.json").read_text())
findings=json.loads((ROOT/"findings.json").read_text())
published={x["id"]:x for x in json.loads((ROOT/"issue-results.json").read_text())}
client=ROOT/"evidence"/"client"/"results"
server=ROOT/"evidence"/"server"/"results"
latest={}
executions=0
for name in ("initial","adapter-smoke","verified","triage","confirm-new","app-helper"):
    for line in (client/f"{name}.jsonl").read_text().splitlines():
        row=json.loads(line)
        executions+=1
        if name not in ("initial","adapter-smoke"):
            latest[row["id"]]={**row,"run":name}
assert len(latest)==len(manifest)==382
assert all(hashlib.sha256((ROOT/"scripts"/m["script"]).read_bytes()).hexdigest()==m["sha256"]
           for m in manifest)
assert all(latest[m["id"]]["sha256"]==m["sha256"] for m in manifest)
by_case={cid:published[f["id"]]["number"] for f in findings for cid in f["cases"]}
exceptions={
    "s103":("representation caveat","Empty R object/array ambiguity; #60 has a nonempty-object proof."),
    "s240":("not established","A generic query exception need not poison the session."),
    "s241":("not a bug","Explicit reuse after close is not prohibited."),
    "s246":("known issue #34","R ignores timeout during session creation."),
    "s247":("known issue #34","R ignores timeout during submission."),
    "s293":("known limitation #44","R executes synchronously and can process multiple queued inputs."),
    "s294":("limitation, not new bug","This generic blocking Python engine has no abort hook."),
    "s295":("limitation, not new bug","This generic blocking R engine has no abort hook."),
    "s304":("UX observation","Run stays enabled, but Python click coalescing passes (#49)."),
    "s305":("UX observation","Disabled button is not an unconditional documented guarantee."),
}
rows=[]
for item in manifest:
    r=latest[item["id"]]
    if r["status"]=="pass":disposition,note="pass",""
    elif item["id"] in by_case:disposition,note="reported",f"#{by_case[item['id']]}"
    else:disposition,note=exceptions[item["id"]]
    rows.append({**item,"status":r["status"],"run":r["run"],
                 "disposition":disposition,"note":note,"seconds":r["seconds"]})
(ROOT/"case-results.json").write_text(json.dumps(rows,indent=2),encoding="utf-8")
with (ROOT/"case-results.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=["id","name","category","status","disposition","note","run","seconds"])
    w.writeheader()
    for r in rows:w.writerow({k:r[k] for k in w.fieldnames})

api=json.loads((server/"api-coverage.json").read_text())
tests=json.loads((server/"pytest-coverage.json").read_text())
function_rows=[]
for path,data in tests["files"].items():
    name=path.split("/sashiny/")[-1]
    for function,d in data.get("functions",{}).items():
        if not function:continue
        s=d["summary"]
        function_rows.append({"module":name,"function":function,
            "covered_statements":s["covered_lines"],"statements":s["num_statements"],
            "percent":round(s["percent_statements_covered"],2)})
with (ROOT/"python-function-coverage.csv").open("w",newline="",encoding="utf-8") as f:
    w=csv.DictWriter(f,fieldnames=list(function_rows[0]))
    w.writeheader();w.writerows(function_rows)
zero=[f"{r['module']}::{r['function']}" for r in function_rows
      if r["statements"] and not r["covered_statements"]]
counts=Counter(r["status"] for r in rows)
categories=sorted({r["category"] for r in rows})
summary={"revision":"dd0bf602379ab3822e23eefec694514874d860f8",
         "scripts":len(rows),"script_executions":executions,"latest_statuses":dict(counts),
         "categories":len(categories),"reported_root_causes":len(findings),
         "new_issues":[p["number"] for p in published.values() if p["action"]=="create"],
         "reopened_issues":[p["number"] for p in published.values() if p["action"]=="reopen"],
         "api_coverage":api["totals"],"pytest_coverage":tests["totals"],
         "source_changes":False}
(ROOT/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")

lines=[
    "# SAShiny detailed two-VM audit",
    "",
    "**Verdict: not release-ready.** The ordinary Python gates pass, but the extended suite "
    "reproduces defects, several previously closed issues remain incomplete, and the fresh R "
    "package check fails for a real installed-fixture mismatch.",
    "",
    "## Scope and provenance",
    "",
    "- Revision: `dd0bf602379ab3822e23eefec694514874d860f8` (public repository, pinned in both testing and reports).",
    "- Server VM: `29e0b068-6553-4b69-bda4-f3dc705727eb`.",
    "- Client VM: `3e6c6025-30b2-4a83-adee-78fd35613278`.",
    "- Python 3.14.10; R 4.5.0; installed source-built Python wheel / R package, not patched source imports.",
    "- Python Shiny 1.9.0 and R Shiny 1.10.0; all declared optional runtime integrations installed.",
    "- API requests and actual Shiny HTTP/WebSocket traffic originated on the second VM.",
    "- No SAS credentials or real clinical/business data were used; all transports/data are synthetic.",
    "- Repository source stayed unchanged. The audit did not merge, publish, or fix package code.",
    "",
    "## Execution totals",
    "",
    f"- **{len(rows)} distinct executable Python scripts**, with unique content hashes in [manifest.json](manifest.json).",
    f"- **{executions} recorded script executions**, including initial calibration and targeted repeats.",
    f"- Latest result for every script: **{counts['pass']} pass, {counts['fail']} failed assertions**.",
    "- Failed assertions are **not** counted as individual bugs: 48 map to the 22 reported root causes; "
    "the remaining 10 are existing work, representation caveats or stronger-than-promised expectations.",
    "- **14 new issues (#70-#83), 8 reopened issues (#51, #53, #54, #59, #60, #63, #68, #69)**. "
    "Additional fresh timing evidence was added to existing #34.",
    "- Every reported API regression was reproduced; new supplemental findings were repeated independently. "
    "The R package-fixture problem is corroborated by the fresh built package and all six R CI jobs.",
    "",
    "See [case-results.csv](case-results.csv) for the full case ledger and adjudication, "
    "[case-results.json](case-results.json) for feature tags and hashes, and [issue-results.json](issue-results.json) for GitHub URLs.",
    "",
    "## Package gates",
    "",
    "| Gate | Actual result |",
    "|---|---|",
    "| Spec checker | 144 passed, 0 failed |",
    "| Python ruff / format / strict mypy | Passed |",
    "| Python pytest | 282 passed, 37 skipped, 5 warnings |",
    "| R development tests (`NOT_CRAN=true`) | 563 passing assertions; 1 error in the pre-run choices test (#68); 8 skips and 11 test warnings |",
    "| R CMD build | Passed |",
    "| Full R CMD check --as-cran, after installing missing documentation tools | **1 ERROR, 1 NOTE**. Installed wrapper fixture mismatch (#81); NOTE is New submission. PDF/HTML manual checks pass. |",
    "",
    "The Python skips are the opt-in live SAS tests and unavailable committed recordings. "
    "The full R package check's test run reports 465 passes and one failure, with CRAN-specific skips.",
    "",
    "The earlier claim that R had only missing-tool problems is **not supported by this clean audit**. "
    "[The audited commit's R CI](https://github.com/procogia/SAShiny/actions/runs/43517892923) "
    "fails on Linux release/oldrel/devel/R 4.1, macOS and Windows.",
    "",
    "## Coverage, with limits",
    "",
    f"- Remote API statement coverage: **{api['totals']['percent_statements_covered']:.2f}%** "
    f"({api['totals']['covered_lines']}/{api['totals']['num_statements']}).",
    f"- Package tests: **{tests['totals']['percent_statements_covered']:.2f}% statement coverage**, "
    f"**{tests['totals']['percent_branches_covered']:.2f}% branch coverage**.",
    "- These are separate coverage runs and must not be added together.",
    "- Shiny processes were also tested over the wire; their successful calls are not all included in "
    "the API/pytest coverage file. In particular, the two final real app-helper servers pass even though "
    "`app.server` is unexecuted in the ordinary pytest coverage report.",
    "- [python-function-coverage.csv](python-function-coverage.csv) lists measured function-level coverage.",
    "- This is a broad feature audit, not proof of 100% of every function/path or every third-party API.",
    "",
    "Functions with zero executed statements in the ordinary pytest coverage run:",
    "",
]
lines.extend("- `"+s+"`" for s in zero)
lines += ["","## Feature matrix","",
          "| Category | Scripts | Pass | Failed assertions |","|---|---:|---:|---:|"]
for category in categories:
    group=[r for r in rows if r["category"]==category]
    lines.append(f"| {category} | {len(group)} | {sum(r['status']=='pass' for r in group)} | "
                 f"{sum(r['status']!='pass' for r in group)} |")
lines += ["","Covered integrations include contract/schema/semantic validation, all seven input types, "
          "all output types, wrappers, log status/scoping, CSV/XLSX/XPT/native sas7bdat readers, "
          "download generation and fake remote file transport, recordings across languages, all "
          "six chart backends/five chart kinds, connection configuration, pools, module UI/overrides, "
          "Shiny lifecycle, four demo tracks and multi-program app helpers.","",
          "## Confirmed findings","",
          "| GitHub | Finding | Scripts |","|---|---|---|"]
for finding in findings:
    p=published[finding["id"]]
    lines.append(f"| [#{p['number']}]({p['url']}) ({p['action']}) | {finding['title']} | "
                 +", ".join(finding["cases"] or ["fresh R package / CI"])+" |")
lines += ["","Full issue bodies are preserved in [issues/](issues/).","",
          "## Failed probes deliberately not filed as new bugs","",
          "| Script | Adjudication |","|---|---|"]
for cid,(kind,note) in exceptions.items():
    lines.append(f"| {cid} | {kind}: {note} |")
lines += ["","## Harness corrections (not product fixes)","",
          "Initial runs exposed mistakes in the test harness. These were corrected and affected cases "
          "were rerun before reporting: a private PNG helper name, untyped zero-valued action-button "
          "initialization, R Plotly JSON serialization, named R data-frame rows in the response adapter, "
          "and PNG transparency compositing. Shell CRLF and an R test-summary exporter were corrected too. "
          "No package source or expected conformance fixture was edited.",
          "",
          "## What is not verified","",
          "- Live SAS authentication, ODA/Viya/9.4 availability, VPN/TLS/SSH connectivity, SAS numerical "
          "results and proprietary formats produced by a real SAS server.",
          "- Killing a real SAS process or every engine-specific cancellation mechanism.",
          "- Every possible input, all dependency versions, and the complete OS matrix from these two Linux VMs.",
          "- Correctness of all functions inside third-party packages. Their SAShiny integrations were exercised.",
          "- A load/throughput SLA; probes are intentionally bounded on 1-vCPU/1-GiB machines.",
          "",
          "## Reproduction and cleanup","",
          "See [README.md](README.md) for running individual scripts or the complete two-VM harness. "
          "Raw evidence lives under [evidence/client/results/](evidence/client/results/) and "
          "[evidence/server/results/](evidence/server/results/). The final manual-complete R log is "
          "[r-check-final.log](evidence/server/results/r-check-final.log).",
          "",
          "Both audit VMs are destroyed after exporting evidence. Their former preview URLs are not "
          "permanent deployments. See [cleanup.json](cleanup.json) for final cleanup verification.",
          ""]
(ROOT/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
print(json.dumps(summary,indent=2))
