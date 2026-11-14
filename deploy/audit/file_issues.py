"""File only the manually triaged findings; persist each result and never blind-retry."""
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent
findings=json.loads((ROOT/"findings.json").read_text())
out=ROOT/"issue-results.json"
saved=json.loads(out.read_text()) if out.exists() else []
done={r["id"] for r in saved if r["state"]=="done"}
if any(r["state"]!="done" for r in saved):
    raise RuntimeError("Uncertain prior operation: inspect GitHub before retrying")
for finding in findings:
    if finding["id"] in done:continue
    item={"id":finding["id"],"state":"submitting","action":finding["action"]}
    saved.append(item)
    out.write_text(json.dumps(saved,indent=2))
    base=["gh","issue"]
    body=ROOT/"issues"/f"{finding['id']}.md"
    if finding["action"]=="create":
        cmd=base+["create","--repo","procogia/SAShiny","--title",finding["title"],
                  "--body-file",str(body)]
        p=subprocess.run(cmd,text=True,capture_output=True,encoding="utf-8")
        if p.returncode:raise RuntimeError(p.stderr)
        link=p.stdout.strip()
        if not link.startswith("https://github.com/procogia/SAShiny/issues/"):
            raise RuntimeError("Uncertain create output: "+link)
        item["url"]=link
        item["number"]=int(link.rsplit("/",1)[1])
    else:
        number=str(finding["issue"])
        subprocess.run(base+["comment",number,"--repo","procogia/SAShiny",
                             "--body-file",str(body)],check=True)
        subprocess.run(base+["reopen",number,"--repo","procogia/SAShiny"],check=True)
        item.update(number=int(number),url=f"https://github.com/procogia/SAShiny/issues/{number}")
    item["state"]="done"
    out.write_text(json.dumps(saved,indent=2))
    print(item["action"],item["number"],finding["title"],flush=True)
