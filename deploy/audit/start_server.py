"""Start only this audit's services; record exact process IDs for cleanup."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path("/tmp/audit")
PY = "/tmp/SAShiny/Python/.venv/bin/python"
os.environ.update(MPLBACKEND="Agg", SASHINY_LIVE="0", NOT_CRAN="true",
                  OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", R_LIBS_USER="/tmp/Rlib")
import spy_app
(ROOT/"spy_contracts.json").write_text(json.dumps({k:v.data for k,v in spy_app.contracts.items()}))
services = {
    "api":[PY,"-m","coverage","run","--concurrency=thread","--source=sashiny",
           "--data-file=/tmp/audit/results/.coverage-api","-m","uvicorn",
           "api:app","--host","0.0.0.0","--port","8000"],
    "python-spy":[PY,"-m","shiny","run","/tmp/audit/spy_app.py","--host","0.0.0.0","--port","8001"],
    "r-spy":["Rscript","-e","shiny::runApp('/tmp/audit/spy_app.R',host='0.0.0.0',port=8002,launch.browser=FALSE)"],
    "python-demo":[PY,"-m","shiny","run","/tmp/SAShiny/Python/examples/demo/app.py","--host","0.0.0.0","--port","8003"],
}
pids = {}
for name,cmd in services.items():
    cwd = "/tmp/audit"
    p = subprocess.Popen(cmd,cwd=cwd,stdout=(ROOT/"results"/f"{name}.log").open("w"),
                         stderr=subprocess.STDOUT,start_new_session=True,env=os.environ.copy())
    pids[name] = p.pid
(ROOT/"pids.json").write_text(json.dumps(pids))
print(pids)
