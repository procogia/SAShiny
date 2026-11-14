import hashlib
import json
import os
import time
from pathlib import Path
from websockets.sync.client import connect

def exercise(language):
    port=8004 if language=="python" else 8005
    api=os.environ["AUDIT_API"]
    url=api.replace("8000-",str(port)+"-").replace("https:","wss:")+"/websocket/"
    states={}
    messages=[]
    data={".clientdata_output_alpha-status_hidden":False,
          ".clientdata_output_beta-status_hidden":False,
          ".clientdata_output_alpha-out_report_hidden":False,
          "alpha-run:shiny.action":0,"beta-run:shiny.action":0}
    with connect(url,open_timeout=15) as ws:
        ws.send(json.dumps({"method":"init","data":data}))
        for module in ("alpha","beta"):
            ws.send(json.dumps({"method":"update","data":{f"{module}-run:shiny.action":1}}))
            deadline=time.monotonic()+8
            while time.monotonic()<deadline:
                try:msg=json.loads(ws.recv(timeout=0.5))
                except TimeoutError:continue
                messages.append(msg)
                states.update(msg.get("values",{}))
                if "status: success" in str(states.get(f"{module}-status","")):break
            assert "status: success" in str(states.get(f"{module}-status","")),states
        if language=="python":
            expected=hashlib.sha256(b"data work.out; run;\n").hexdigest()
            deadline=time.monotonic()+3
            while expected not in str(states.get("alpha-out_report","")) and time.monotonic()<deadline:
                try:msg=json.loads(ws.recv(timeout=0.2))
                except TimeoutError:continue
                messages.append(msg);states.update(msg.get("values",{}))
            assert expected in str(states["alpha-out_report"]),states
    result=Path(os.environ.get("AUDIT_RESULTS","/tmp/audit/results"))/"http"
    result.mkdir(exist_ok=True)
    (result/(os.environ.get("AUDIT_CASE_ID","app")+"-wire.json")).write_text(json.dumps(messages))
