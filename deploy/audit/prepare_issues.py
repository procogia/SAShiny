"""Prepare reviewed, reproducible issue bodies from the preserved audit evidence."""
import ast
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SHA="dd0bf602379ab3822e23eefec694514874d860f8"
manifest={r["id"]:r for r in json.loads((ROOT/"manifest.json").read_text())}
findings=json.loads((ROOT/"findings.json").read_text())
results=ROOT/"evidence"/"client"/"results"
latest={}
for name in ("verified","triage","confirm-new"):
    for line in (results/f"{name}.jsonl").read_text().splitlines():
        r=json.loads(line)
        latest[r["id"]]=r


def compact(value,key=""):
    if isinstance(value,dict):
        return {k:compact(v,k) for k,v in value.items()
                if k not in ("traceback","stderr","program_b64","seconds","started_at","ended_at")}
    if isinstance(value,list):
        return [compact(v,key) for v in value[:8]]+(
            [f"... {len(value)-8} additional entries in raw evidence"] if len(value)>8 else [])
    if isinstance(value,str) and len(value)>360:
        return value[:360]+" ... [truncated; full value in audit evidence]"
    return value


out=ROOT/"issues"
out.mkdir(exist_ok=True)
for finding in findings:
    for cid in finding["cases"]:
        assert cid in latest and latest[cid]["status"]=="fail",(finding["id"],cid)
    lines=[f"# {finding['title']}","",
        f"Re-tested at **`{SHA}`**, using two separate Daytona VMs: "
        "one hosting installed R/Python SAShiny packages plus their optional backends, "
        "the other sending HTTP/WebSocket requests. Package source was not patched by this audit.",
        "",
        "Environment: Python 3.14.10 / SAShiny 0.1.6 built from the pinned commit; "
        "R 4.5.0 / SAShiny 0.1.5; Python Shiny 1.9.0 and R Shiny 1.10.0. "
        "SAS orchestration tests use the actual SaspyEngine with a synthetic transport; "
        "**no live/licensed SAS result is claimed**.",
        "","## Reproduced behavior","",finding["summary"],"","## Expected","",
        finding["expected"],"",f"Basis: {finding['spec']}.","",
        "## Impact","",finding["impact"],"","## Reproduction and evidence",""]
    if finding.get("wire"):
        lines += ["These cases use the real Shiny websocket and session download/upload HTTP routes. "
                  "Initialization sends `run:shiny.action = 0` (the real action-button wire type), "
                  "so a before-first-run test cannot accidentally trigger a run.",""]
        for cid in finding["cases"]:
            if finding["id"] == "r-choices-message":
                evidence = {"language":"r","before_first_run":True,
                            "broken-status":"absent/empty (expected choices-load error)"}
            elif finding["id"] == "upload-transport":
                evidence = {"language":"python" if cid=="s306" else "r",
                            "max_size_mb":0.1,"uploaded_bytes":160000,"http_status":200}
            else:
                match=re.search(r"AssertionError: (.+)",latest[cid]["stderr"])
                observed=ast.literal_eval(match.group(1))
                evidence={"language":"python" if cid=="s296" else "r",
                          "http_status":observed[0],"body":observed[2][:150],
                          "headers":{k:v for k,v in observed[1].items()
                                     if k in ("content-type","content-disposition")}}
            lines += [f"**{cid}: {manifest[cid]['name']}**","",
                      "```json",json.dumps(evidence,indent=2),"```",""]
    else:
        for cid in finding["cases"][:3]:
            p=results/"http"/f"{cid}.jsonl"
            if not p.exists():continue
            per_language={}
            for line in p.read_text().splitlines():
                r=json.loads(line)
                per_language[r["language"]]=r
            lines += [f"**{cid}: {manifest[cid]['name']}**","",
                "The test-only `/invoke/<language>/<operation>` adapter calls the corresponding "
                "package function directly; it does not repair or replace validation behavior.","",
                "Input:","```json",json.dumps(compact(next(iter(per_language.values()))["request"]),
                                             ensure_ascii=False,indent=2),"```",""]
            for lang,r in per_language.items():
                payload=r["response"]
                if finding["id"]=="timeout-generation":
                    v=payload["value"]
                    payload={"old_status":v["old"]["status"],"new_status":v["new"]["status"],
                             "sessions_created":v["sessions_created"],
                             "closed_before_cleanup":v["closed_before_cleanup"]}
                if finding["id"]=="chart-mappings":
                    v=payload.get("value",{})
                    if "png" in v:
                        payload={"note":"Rendered pixel equality / axis count is asserted by the script.",
                                 "axes":v.get("axes")}
                    elif "plot" in v:
                        payload={"trace_count":len(v["plot"].get("data",[])),
                                 "axis_keys":[k for k in v["plot"].get("layout",{}) if k.startswith("xaxis")]}
                lines += [f"{lang} (`{r['operation']}`):","```json",
                          json.dumps(compact(payload),ensure_ascii=False,indent=2),"```",""]
    if finding.get("evidence_note"):
        lines += [finding["evidence_note"],""]
    if finding["id"] == "timeout-generation":
        source=(ROOT/"ops_py.py").read_text()
        fn=source.split("def generation_case(",1)[1].split("\ndef dispatch(",1)[0]
        lines += ["The exact Event-based reproduction used by the adapter is below. "
                  "`FakeSAS` is the existing `Python/tests/fakesas.py` test double; "
                  "`contract` has a trivial program and `run.timeout_seconds: 1`.",
                  "```python","import dataclasses, threading, time",
                  "import sashiny","def generation_case("+fn.strip(),"```",""]
    if finding.get("ci"):
        lines += [f"Independent CI evidence: {finding['ci']}.",""]
    if finding["id"]=="r-package-fixtures":
        lines += ["Installed-package failure (also reproduced in the server VM):","```text",
                  'actual:   %ae_table(ADSL_DS=%bquote(&ADSL_DS), ARM=%bquote(&ARM));',
                  'expected: %ae_table(ADSL_DS=&ADSL_DS, ARM=&ARM);',
                  "```","The root fixture has the new call; the tracked `R/inst/spec` copy has the old one.",""]
    lines += ["## Source locations",""]
    for path in finding["sources"]:
        lines.append(f"- [{path}](https://github.com/procogia/SAShiny/blob/{SHA}/{path})")
    lines += ["","## Verification expectation","",
              "Add focused regression coverage for the input(s) above in both applicable language paths. "
              "Re-run the standalone audit script(s), not just a constructor/import smoke test. "
              "Do not change existing fixture expectations to match a failing implementation.",
              "", "Audit case IDs: "+", ".join(finding["cases"] or ["installed R package check"])+".",""]
    (out/f"{finding['id']}.md").write_text("\n".join(lines),encoding="utf-8")
print("Prepared",len(findings),"issue bodies")
