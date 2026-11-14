"""Run every manifest script separately; never turn failures into silent passes."""
import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument("--only",default="")
parser.add_argument("--label",default="initial")
args=parser.parse_args()
root=Path(__file__).resolve().parent
out=root/"results"
out.mkdir(exist_ok=True)
manifest=json.loads((root/"manifest.json").read_text())
if args.only:
    chosen=set(args.only.split(","))
    manifest=[m for m in manifest if m["id"] in chosen or m["category"] in chosen]
results=[]
with (out/f"{args.label}.jsonl").open("w") as stream:
    for case in manifest:
        start=time.monotonic()
        env={**os.environ,"PYTHONPATH":str(root),"AUDIT_CASE_ID":case["id"],
             "AUDIT_RESULTS":str(out)}
        try:
            p=subprocess.run([sys.executable,str(root/"scripts"/case["script"])],
                             cwd=root,env=env,capture_output=True,text=True,timeout=120)
            result={**case,"status":"pass" if p.returncode==0 else "fail",
                    "returncode":p.returncode,"stdout":p.stdout[-6000:],"stderr":p.stderr[-12000:]}
        except subprocess.TimeoutExpired as e:
            result={**case,"status":"timeout","stderr":str(e)}
        result["seconds"]=round(time.monotonic()-start,3)
        stream.write(json.dumps(result)+"\n"); stream.flush()
        results.append(result)
        print(f"{case['id']} {result['status']} {case['name']}",flush=True)
summary={"total":len(results),"counts":dict(Counter(r["status"] for r in results)),
         "categories":dict(Counter(r["category"] for r in results))}
(out/f"{args.label}-summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary),flush=True)
