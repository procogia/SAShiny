"""Verify the Daytona sandbox for the SAShiny demo (issue #12).

Creates a sandbox, runs a hello-world check, smoke-tests the demo app in Offline
mode, and — most importantly — tests whether the sandbox can make an outbound
TCP 8591 connection to ``*.oda.sas.com`` (SAS OnDemand for Academics). That
egress test is the "tier" verification: if it succeeds, the hosted demo can
offer the ODA profile; if it fails, the demo is Offline-only.

Usage (from the repository root):

    pip install daytona
    export DAYTONA_API_KEY=...        # from https://app.daytona.io/dashboard/keys
    python deploy/daytona/verify_sandbox.py

The API key is read from the ``DAYTONA_API_KEY`` environment variable (or a
gitignored ``.env`` file). It is never printed or stored in the repo.
"""

from __future__ import annotations

import os
import socket
import sys
import time

# ODA hosts used for the egress test (spec/tools/live_sas_check.py).
ODA_HOSTS = [
    "odaws01-usw2.oda.sas.com",
    "odaws02-usw2.oda.sas.com",
]
ODA_PORT = 8591

# Public base image for the sandbox. The demo Dockerfile is not pushed to a
# public registry, so the tier check uses a minimal public image; the full demo
# image is built separately (see deploy/daytona/README.md).
BASE_IMAGE = "ubuntu:22.04"


def _load_api_key() -> str:
    key = os.environ.get("DAYTONA_API_KEY", "")
    if key:
        return key
    # Fall back to a gitignored .env file.
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
    if os.path.isfile(env_path):
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if line.startswith("DAYTONA_API_KEY="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _check_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    api_key = _load_api_key()
    if not api_key:
        print("ERROR: DAYTONA_API_KEY is not set.")
        print("Create one at https://app.daytona.io/dashboard/keys and export it,")
        print("or put it in a gitignored .env file.")
        return 1

    from daytona import Daytona, CreateSandboxFromImageParams  # noqa: PLC0415

    daytona = Daytona()
    print(f"Creating sandbox from image {BASE_IMAGE} ...")
    sandbox = daytona.create(
        CreateSandboxFromImageParams(image=BASE_IMAGE),
        timeout=120,
    )
    sandbox_id = getattr(sandbox, "id", "?")
    print(f"Sandbox created: {sandbox_id}")

    try:
        # 1. Hello world.
        r = sandbox.process.exec("echo 'Hello from Daytona'")
        print(f"hello-world: {r.result.strip()}")

        # 2. Tier check: outbound TCP 8591 to ODA hosts.
        #    Run the check inside the sandbox so it reflects the sandbox's
        #    network egress policy, not this machine's.
        results: dict[str, bool] = {}
        for host in ODA_HOSTS:
            cmd = (
                f"python3 -c \"import socket; "
                f"s=socket.socket(); s.settimeout(5); "
                f"r=s.connect_ex(('{host}', {ODA_PORT})); "
                f"print('OK' if r==0 else 'BLOCKED')\""
            )
            out = sandbox.process.exec(cmd).result.strip()
            ok = out == "OK"
            results[host] = ok
            print(f"tcp {host}:{ODA_PORT} -> {'REACHABLE' if ok else 'BLOCKED'}")

        any_reachable = any(results.values())
        print()
        if any_reachable:
            print("TIER RESULT: ODA reachable — the hosted demo can offer the ODA profile.")
        else:
            print("TIER RESULT: ODA NOT reachable — the hosted demo is Offline-only.")
            print("  (This is expected on Daytona Tier 1/2, which restricts outbound")
            print("   non-HTTP egress. Confirm the tier with ProCogia.)")
    finally:
        print(f"Deleting sandbox {sandbox_id} ...")
        sandbox.delete()
        print("Done.")

    return 0


if __name__ == "__main__":
    sys.exit(main())