#!/usr/bin/env bash
# Run the SAShiny Shiny test client on a Daytona VM (issue #9).
#
# Installs the dev Shiny (with the test server), installs the SAShiny package,
# and runs the module test client. Run from the repository root:
#
#   bash deploy/daytona/run_module_tests.sh
#
# Assumes the SAShiny source is available at /app (mounted or copied).

set -euo pipefail

echo "Installing dev Shiny (with test server) ..."
pip3 install --quiet "git+https://github.com/posit-dev/py-shiny.git"

echo "Installing SAShiny ..."
pip3 install --quiet -e /app/Python

echo "Running the module test client ..."
cd /app/Python
python3 -m pytest tests/test_module_client.py -v