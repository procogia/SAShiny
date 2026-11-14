"""Retrieve audit-only evidence without displaying base64 or credentials."""
import base64
import subprocess
import sys
import zipfile
from pathlib import Path

sandbox, label = sys.argv[1:3]
if label not in ("server","client"):
    raise ValueError(label)
cmd="cd /tmp/audit && python -m zipfile -c /tmp/audit/evidence.zip results"
subprocess.run(["daytona","exec","--cwd","/tmp","--timeout","60",sandbox,"--","sh","-c",cmd],check=True)
p=subprocess.run(["daytona","exec","--cwd","/tmp","--timeout","60",sandbox,"--",
                  "base64","-w0","/tmp/audit/evidence.zip"],check=True,capture_output=True)
dest=Path(__file__).resolve().parent/"evidence"/label
dest.mkdir(parents=True,exist_ok=True)
archive=dest/"evidence.zip"
archive.write_bytes(base64.b64decode(p.stdout,validate=True))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for n in z.namelist():
        if ".." in Path(n).parts or Path(n).is_absolute():
            raise ValueError(n)
    z.extractall(dest)
print(label,"evidence:",archive.stat().st_size,"bytes")
