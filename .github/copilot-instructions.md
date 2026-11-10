# Copilot instructions for SAShiny

SAShiny lets an **unchanged SAS program** act as the server of a Shiny app (R and Python). A sidecar YAML
contract (`<program>.sashiny.yml`) declares inputs and outputs. Read these before writing code:

1. `spec/CONTRACT.md`: the **normative** spec. If code and spec disagree, the spec wins.
2. `spec/sashiny.schema.json`: the contract structure.
3. `spec/fixtures/`: the conformance tests. Both languages must pass all of them.
4. `PLAN.md`: architecture, decisions log (D1–D29) and roadmap. Open work is tracked in GitHub issues.

## Non-negotiable rules

- **Never modify, rewrite or reformat a user's SAS program.** Submit its text verbatim inside the wrapper (spec §6.3).
- **Spec first.** A behaviour change starts in `spec/CONTRACT.md` and its fixtures, then R and Python follow.
  Never edit a fixture's expected output to make an implementation pass. Write expected outputs by hand from the spec.
- **Security.** User values reach SAS only as single-quoted `call symputx` literals, then `%superq` (spec §6.3).
  Never interpolate user text into SAS code any other way. Validate every value (V001–V014) before rendering.
- **Byte-exact wrapper.** Generated SAS must match `spec/fixtures/wrapper/*/expected_*.sas` exactly (LF line endings, no trailing spaces).
- **No SAS in automated checks.** CRAN, PyPI and CI use the mock engine. Live-SAS tests are opt-in (`SASHINY_LIVE=1`).
- **No credentials** in code, contracts, tests, logs or reports. They come from `~/.authinfo` or the platform's secret store.
- R and Python must behave identically. Implement a feature in both, or open an issue for the missing side.

## Layout

| Path | Contents |
|---|---|
| `R/` | R package root (CRAN). Code in `R/R/`, tests in `R/tests/testthat/` |
| `Python/` | Python library root (PyPI). Code in `Python/src/sashiny/`, tests in `Python/tests/` |
| `spec/` | Contract spec, schema, fixtures; `spec/tools/` = reference oracle + checkers (never shipped) |
| `examples/` | general / pharma / aml demo programs + contracts + synthetic data |

Planned modules (same names in both languages where possible): contract (load + validate), values (validate +
render), wrapper (reset + main code), lint (L001–L005), engines (mock, saspy), pool, run, result, Shiny modules
(auto-UI + custom override), app helpers.

## R conventions (target: CRAN)

- R >= 4.1. Native pipe `|>` is allowed. Tidyverse style; `lintr` + `styler`; line length 100.
- roxygen2 (markdown) docs for **every** function, exported and internal. Use `@noRd` for internal ones.
  Add `@examples` / `@examplesIf` that run in under 5 s without SAS.
- testthat 3e. Fixture-conformance tests read `../spec/fixtures` in development. At build time spec files are copied to `inst/spec/`.
- Keep hard `Imports` minimal. Put optional backends (`reticulate`, `mirai`, `bslib`, `DT`, `haven`, `openxlsx`) in `Suggests`,
  guarded with `rlang::check_installed()`.
- CRAN policy: write only to `tempdir()`, no internet in checks, restore any `options()`/`par()`/working directory you change,
  put software names in single quotes in DESCRIPTION (`'SAS'`, `'Shiny'`, `'SASPy'`).
- Gate before every PR: `R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz`. Allowed: 0 errors, 0 warnings,
  and only the "new submission" or development-version NOTE.

## Python conventions (target: PyPI)

- Python >= 3.10. `src/` layout, hatchling, uv. Type hints everywhere (`mypy --strict`); ships `py.typed`.
- ruff for lint and format (config in `Python/pyproject.toml`); Google-style docstrings; pytest.
- Optional extras: `sashiny[saspy]`. Core must import without saspy installed.
- Shiny for Python: `@module.ui` / `@module.server`, `reactive.calc` / `reactive.effect`, `@reactive.extended_task` for SAS runs.
- Gate before every PR: `cd Python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`.

## Spec gate

`uv run --no-project --with jsonschema --with pyyaml python spec/tools/check_spec.py` must pass.

## Commits and PRs

Imperative commit messages, one logical change each. Reference the spec section (e.g. "§6.3") and the issue (`#n`).
Every PR description lists which fixtures it makes pass and which gates were run.
