"""Transfer audit-owned archives using the already-authenticated Daytona CLI."""
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

archive = Path(sys.argv[1])
sandbox = sys.argv[2]
destination = sys.argv[3]
if not destination.startswith("/tmp/audit/") or not destination.endswith(".zip"):
    raise ValueError("destination must be an audit ZIP in /tmp/audit")
encoded = base64.b64encode(archive.read_bytes()).decode("ascii")
for offset in range(0, len(encoded), 12000):
    operator = ">" if offset == 0 else ">>"
    command = f"mkdir -p /tmp/audit; echo {encoded[offset:offset+12000]} | base64 -d {operator} {destination}"
    subprocess.run(["daytona","exec","--cwd","/tmp","--timeout","45",sandbox,"--","sh","-c",command],
                   check=True)
run = subprocess.run(["daytona","exec","--cwd","/tmp","--timeout","45",sandbox,"--","sh","-c",
                      f"sha256sum {destination}; python -m zipfile -e {destination} /tmp/audit"],
                     check=True,text=True,capture_output=True)
expected = hashlib.sha256(archive.read_bytes()).hexdigest()
assert expected in run.stdout, (expected,run.stdout)
print(f"Verified {archive.name}: {archive.stat().st_size} bytes, SHA256 {expected}")
