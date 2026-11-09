#!/usr/bin/env bash
# Verify the Daytona tier for the SAShiny demo (issue #12) via the CLI.
#
# Creates a sandbox, tests outbound TCP 8591 to the ODA hosts from inside it,
# and deletes the sandbox. Uses the authenticated Daytona CLI (no SDK API key
# needed). Run from the repository root:
#
#   bash deploy/daytona/verify_tier_cli.sh
#
# Result: prints "ODA reachable" (hosted demo can offer ODA) or "ODA NOT
# reachable" (Offline-only). No credentials are stored or printed.

set -euo pipefail

NAME="sashiny-tier-check-$(date +%s)"
ODA_HOSTS=("odaws01-usw2.oda.sas.com" "odaws02-usw2.oda.sas.com")
PORT=8591

cleanup() {
  echo "Deleting sandbox $NAME ..."
  daytona delete "$NAME" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Creating sandbox $NAME ..."
daytona create --name "$NAME" --auto-stop 15 >/dev/null

reachable=0
for host in "${ODA_HOSTS[@]}"; do
  out=$(daytona exec "$NAME" -- python3 -c \
    "import socket; s=socket.socket(); s.settimeout(5); print('OK' if s.connect_ex(('$host', $PORT)) == 0 else 'BLOCKED')")
  echo "tcp $host:$PORT -> $out"
  if [ "$out" = "OK" ]; then
    reachable=1
  fi
done

echo
if [ "$reachable" -eq 1 ]; then
  echo "TIER RESULT: ODA reachable — the hosted demo can offer the ODA profile."
else
  echo "TIER RESULT: ODA NOT reachable — the hosted demo is Offline-only."
fi