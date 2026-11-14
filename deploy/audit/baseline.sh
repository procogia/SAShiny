#!/bin/sh
set -u
cd /tmp/SAShiny/Python
export R_LIBS_USER=/tmp/Rlib
export RETICULATE_PYTHON=/tmp/SAShiny/Python/.venv/bin/python
export SASHINY_LIVE=0
export MPLBACKEND=Agg
export OPENBLAS_NUM_THREADS=1
export OMP_NUM_THREADS=1
OUT=/tmp/audit/results
.venv/bin/ruff check . > "$OUT/ruff.log" 2>&1
printf 'ruff %s\n' "$?" >> "$OUT/baseline-status.txt"
.venv/bin/ruff format --check . > "$OUT/ruff-format.log" 2>&1
printf 'ruff-format %s\n' "$?" >> "$OUT/baseline-status.txt"
.venv/bin/mypy > "$OUT/mypy.log" 2>&1
printf 'mypy %s\n' "$?" >> "$OUT/baseline-status.txt"
.venv/bin/python -m pytest --cov=sashiny --cov-branch --cov-report=json:/tmp/audit/results/pytest-coverage.json --junitxml=/tmp/audit/results/pytest.xml -q > "$OUT/pytest.log" 2>&1
printf 'pytest %s\n' "$?" >> "$OUT/baseline-status.txt"
.venv/bin/python /tmp/SAShiny/spec/tools/check_spec.py > "$OUT/spec.log" 2>&1
printf 'spec %s\n' "$?" >> "$OUT/baseline-status.txt"
cd /tmp/audit
Rscript /tmp/audit/baseline.R > "$OUT/testthat.log" 2>&1
printf 'testthat %s\n' "$?" >> "$OUT/baseline-status.txt"
R CMD build /tmp/SAShiny/R > "$OUT/r-build.log" 2>&1
printf 'R-build %s\n' "$?" >> "$OUT/baseline-status.txt"
if [ -f SAShiny_0.1.5.tar.gz ]; then
  R CMD check --as-cran SAShiny_0.1.5.tar.gz > "$OUT/r-check.log" 2>&1
  printf 'R-check %s\n' "$?" >> "$OUT/baseline-status.txt"
  cp SAShiny.Rcheck/00check.log "$OUT/00check.log"
fi
printf 'BASELINE COMPLETE\n'
