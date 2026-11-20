# Contributing to SAShiny

## Ground rules

1. **The spec comes first.** Any behaviour change starts as a change to `spec/CONTRACT.md` and its
   fixtures. Then R and Python are updated to pass. Both languages must pass every fixture.
2. **SAS programs are never modified** by SAShiny code. No transpiling, reformatting or rewriting.
3. **No SAS in automated checks.** CRAN, PyPI and CI checks run against the mock engine. Live-SAS
   tests are opt-in (`SASHINY_LIVE=1`) and skipped otherwise.
4. **Security is not optional.** User values reach SAS only through the quoting scheme in spec §6.3.
   Every new input type needs adversarial fixtures.

## Style

- R: tidyverse style, `lintr` and `styler`, roxygen2 docs for every function (exported and internal),
  testthat 3e.
- Python: `ruff` (lint + format), `mypy --strict`, Google-style docstrings, pytest.
- Commits: imperative mood, one logical change per commit. Reference the spec section when relevant.

## Adding a fixture

Write the expected output **by hand** from CONTRACT.md, then run
`uv run --no-project --python 3.12 --with jsonschema --with pyyaml python spec/tools/check_spec.py`.
Never generate expected files from an implementation.

## Live checks

Live tests need a real, licensed SAS session and are skipped everywhere else (CI, CRAN, PyPI). Set
`SASHINY_LIVE=1` and `SASHINY_PROFILE` (`oda`, `viya` or `sas94`, with the variables listed in
`Python/tests/live/conftest.py`); credentials come from `~/.authinfo`.

Session reuse (#130 J1/J2) runs `examples/general` 10 times on one engine and on a pool of two. It
prints the distinct SAS process ids and the median and p90 run times, and writes a CSV to the temp
folder:

```sh
cd Python && SASHINY_LIVE=1 SASHINY_PROFILE=oda uv run --extra saspy pytest tests/live/test_live_session_reuse.py -s
cd R && SASHINY_LIVE=1 SASHINY_PROFILE=oda Rscript -e 'testthat::test_file("tests/testthat/test-live-session-reuse.R")'
```

Record the summary (backend, date, process ids, timings) in the PR or in `docs/qa-live-checklist.md`.

PROC PYTHON (#128) runs inside SAS, so pytest cannot drive it. Submit
`Python/tests/live/procpython/probe.sas` in a SAS Viya job (set `repo` first). It answers the #128
probe questions and writes `sashiny_parity_*.json` to WORK. Copy those files locally, then compare
them with saspy:

```sh
cd Python && SASHINY_LIVE=1 SASHINY_PROFILE=viya SASHINY_PROCPYTHON_OUT=<folder> \
  uv run --extra saspy pytest tests/live/test_procpython_live.py
```
Mock-engine tests prove wiring only; they are never live acceptance.
