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
`uv run --no-project --with jsonschema --with pyyaml python spec/tools/check_spec.py`.
Never generate expected files from an implementation.
