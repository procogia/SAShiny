"""Generate every deployment target on examples/general for the CI lint job (spec §6.8).

Writes one folder per target under the given output directory, using an
example profile per target (Viya for Python-only targets, ODA otherwise).
Never shipped; no network, no credentials.
"""

from __future__ import annotations

import sys
from pathlib import Path

from sashiny import deploy as d

REPO = Path(__file__).resolve().parents[2]
ODA = {"name": "oda", "method": "iom", "oda_region": "us1"}
VIYA = {"name": "viya", "method": "http", "url": "https://viya.example.com"}


def main(out: Path) -> int:
    """Generate all targets into ``out``; return the process exit status."""
    app = REPO / "examples" / "general"
    for target in d.targets():
        profile = ODA if target.needs_java_runtime else VIYA
        dest = out / target.id
        res = d.deploy(app, target.id, dest, profile, license_ack=True, language="python")
        print(f"{target.id}: {len(res.files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
