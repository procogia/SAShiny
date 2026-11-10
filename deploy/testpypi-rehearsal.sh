#!/usr/bin/env bash
# TestPyPI rehearsal for the SAShiny Python library.
#
# Builds the distributions and uploads them to TestPyPI (not the real PyPI) so
# the release process can be rehearsed before the real submission. Requires a
# TestPyPI API token in the TWINE_PASSWORD environment variable (or a configured
# ~/.pypirc).
#
# Run from the repository root:
#
#   export TWINE_USERNAME=__token__
#   export TWINE_PASSWORD=pypi-...   # TestPyPI token
#   bash deploy/testpypi-rehearsal.sh

set -euo pipefail

cd Python

echo "Building distributions ..."
uv build

echo "Uploading to TestPyPI ..."
uv publish --publish-url https://test.pypi.org/legacy/ --token "${TWINE_PASSWORD:-}"

echo "Done. Verify with:"
echo "  uv pip install --index-url https://test.pypi.org/simple/ sashiny"