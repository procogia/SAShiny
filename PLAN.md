# SAShiny — Project Plan (Draft v0.1)

> Status: **draft for review**. Open decisions are listed in [Section 10](#10-open-decisions). Nothing below the
> scaffold is built until those are answered.

## 1. Vision

SAShiny lets a SAS program act as the **server** of a Shiny app while Shiny (R or Python) handles
**only the UI**. The SAS program **keeps its form**: it stays a normal `.sas` file that still runs
unchanged in SAS Studio, Enterprise Guide or batch. SAShiny adds a thin, declarative contract around it.

```
┌──────────────────────────┐        ┌───────────────────────────┐        ┌──────────────────────┐
│  Shiny UI (R or Python)  │ inputs │  SAShiny bridge           │  code  │  SAS (9.4 / Viya /   │
│  modules, layout, theme  │ ─────▶ │  contract · validation ·  │ ─────▶ │  local batch)        │
│                          │ ◀───── │  session pool · results   │ ◀───── │  the unchanged .sas  │
│  tables, plots, log view │ outputs│  parsing (log/ODS/data)   │ results│  program             │
└──────────────────────────┘        └───────────────────────────┘        └──────────────────────┘
```

Equivalent mental model: `ui.R` stays in R/Python; `server.R` becomes `analysis.sas`.

## 2. Design principles

1. **SAS stays SAS.** No transpiling, no rewriting. Contract metadata lives in SAS comments.
2. **Same contract, two languages.** One language-neutral spec; R and Python implementations conform to
   shared test fixtures, so behaviour is identical.
3. **Shiny-native.** Everything is a Shiny module (`NS()`/`moduleServer()` in R,
   `@module.ui`/`@module.server` in Python). Results are reactives; long runs use
   `ExtendedTask` (R ≥ 1.8.1) / `@reactive.extended_task` (Python) so the UI never blocks.
4. **Backend-agnostic.** Pluggable engines; a **mock engine** ships in-package so CRAN/PyPI checks,
   examples and tests run with **no SAS installed**.
5. **Secure by default.** Inputs are type-validated and macro-quoted before reaching SAS (no macro/code injection).
6. **CRAN- and PyPI-clean from day one**, not retrofitted.

## 3. The SAS program contract (core idea)

A SAS file declares its interface with structured comments (roxygen-style), so it remains valid SAS:

```sas
/*@sashiny
  @title   Survival summary by treatment arm
  @input   arm      type=choice   choices="Placebo,Drug A,Drug B" default="Placebo" label="Treatment arm"
  @input   cutoff   type=numeric  min=0 max=365 default=90      label="Day cutoff"
  @input   adsl     type=dataset  label="Upload ADSL"            optional
  @output  summary  type=table    from=work.summary
  @output  km_plot  type=plot     from=ods.sgplot
  @output  log      type=log
*/

%let arm    = Placebo;   /* defaults keep the program runnable standalone */
%let cutoff = 90;

proc means data=work.adsl(where=(arm="&arm" and day<=&cutoff)) ...;
run;
```

At runtime SAShiny:
1. Parses the header → builds an **input spec** and **output spec**.
2. (Optional) **auto-generates** Shiny UI controls from the spec, or you bind your own UI.
3. On run: validates inputs, emits safe `%let` statements (quoted via `%nrstr`/`%superq` rules) and uploads
   dataset inputs to `WORK`, then submits the unchanged program.
4. Collects outputs: SAS datasets → data frames; ODS HTML/SVG/PNG → rendered output; log → parsed
   (ERROR/WARNING/NOTE) for a log panel and error surfacing.

The contract is defined once in `spec/` (JSON Schema + fixtures) and implemented in both languages.

## 4. Architecture layers (both languages)

| Layer | Responsibility | R | Python |
|---|---|---|---|
| Contract | Parse `@sashiny` header, validate spec | `sas_contract()` | `sashiny.contract` |
| Engine | Talk to SAS | `sas_engine_*()` | `sashiny.engines` |
| Runner | Inject inputs, submit, collect results | `sas_run()` | `sashiny.run()` |
| Results | Typed results object (data, ODS, log) | S3 class `sashiny_result` | dataclass `Result` |
| Shiny modules | UI + server modules, auto UI | `sas_module_ui/server()` | `@module.ui/server` |
| App helpers | One-liner app from a `.sas` file | `sas_app("x.sas")` | `sashiny.app("x.sas")` |

### Engines (candidates — see decisions)
- **saspy** (official SAS Python client): SAS 9.4 IOM/STDIO/SSH and Viya HTTP. Native in Python; in R via
  `reticulate` (as `sasr` and `sasquatch` do).
- **Viya Compute REST API**: pure HTTP (`httr2` / `httpx`); no Python or Java dependency in R.
- **Local batch**: `sas -sysin file.sas` via `processx` / `subprocess` (simple, single-user).
- **Mock**: deterministic canned results for tests, examples, vignettes, and demos without SAS.

### Session handling
Per Shiny session SAS connection (or a bounded pool), idle timeout, cleanup on `onSessionEnded`,
per-user `WORK` isolation, concurrency limits.

## 5. Repository layout (monorepo)

```
SAShiny/
├── R/                         # the R package root (what CRAN receives)
│   ├── DESCRIPTION  NAMESPACE  LICENSE  NEWS.md  README.Rmd  cran-comments.md
│   ├── R/                     # contract.R, engine-*.R, run.R, result.R, mod-*.R, app.R, utils-*.R
│   ├── inst/sas/              # example .sas programs
│   ├── inst/app/www/          # CSS/JS assets
│   ├── man/                   # roxygen2-generated
│   ├── tests/testthat/        # unit + testServer() module tests (+ shinytest2 off-CRAN)
│   ├── vignettes/             # getting-started, writing-contracts, engines, deployment
│   └── .Rbuildignore
├── Python/                    # the Python library root (what PyPI receives)
│   ├── pyproject.toml  README.md  LICENSE  CHANGELOG.md
│   ├── src/sashiny/           # contract.py, engines/, run.py, result.py, modules.py, app.py
│   ├── tests/                 # pytest (+ playwright e2e off-CI-default)
│   ├── examples/
│   └── docs/                  # mkdocs / quartodoc
├── spec/                      # (proposed) language-neutral contract schema + shared fixtures
├── examples/                  # (proposed) shared .sas demo programs
├── .github/workflows/         # R-CMD-check matrix, pytest matrix, pkgdown, docs, release
├── README.md  PLAN.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md
```

Install from GitHub before release:
- R: `pak::pak("meharpsingh/SAShiny/R")` or `remotes::install_github("meharpsingh/SAShiny", subdir = "R")`
- Python: `pip install "git+https://github.com/meharpsingh/SAShiny#subdirectory=Python"`

## 6. Lessons borrowed from Shiny for Python

- **Decorator modules** (`@module.ui` / `@module.server`) → R side mirrors with clear `*_ui()`/`*_server()` pairs.
- **Explicit reactive types** (`reactive.calc`, `reactive.effect`, `reactive.value`) → we name our reactive
  returns explicitly and document what each module returns.
- **Express vs Core** → offer a one-liner `sas_app("analysis.sas")` (express-like) *and* composable modules (core-like).
- **Extended tasks** for long SAS jobs, with cancel and progress.
- **Type hints + `src/` layout** in Python; equivalent rigor in R via `checkmate`/`rlang` argument checks.

## 7. CRAN readiness checklist (R)

- `R CMD check --as-cran`: 0 errors, 0 warnings, 0 notes (except "New submission").
- DESCRIPTION: Title Case title, no "for R"; software names in single quotes (`'SAS'`, `'Shiny'`);
  `Authors@R` with `aut`, `cre`, `cph` roles; standard license; `URL` + `BugReports`.
- Tests/examples/vignettes **never require SAS**: mock engine; `skip_if_not(sas_available())`, `skip_on_cran()`.
- Examples run fast (< 5 s each); avoid `\dontrun{}` except where truly unavoidable; prefer `@examplesIf`.
- No writing outside `tempdir()`; no changing user options/par/wd without restoring; no internet in checks.
- Minimal hard `Imports`; optional backends (`reticulate`, `httr2`, `processx`) in `Suggests` with
  `rlang::check_installed()`.
- Check on win-builder (release + devel), macOS builder, R-hub, GitHub Actions matrix.
- `cran-comments.md`, `NEWS.md`, `pkgdown` site, `urlchecker`, `spelling`, `goodpractice`, `lintr`/`styler`.
- Trademark notices for SAS® and Shiny® in README and DESCRIPTION/docs where relevant.

## 8. PyPI readiness checklist (Python)

- `pyproject.toml` (PEP 621), `src/` layout, build backend (hatchling proposed).
- Supported Python versions matrix; type hints + `py.typed`; `ruff`, `mypy`, `pytest`, coverage.
- Optional extras: `pip install sashiny[saspy]`, `sashiny[viya]`.
- Publish via GitHub Actions **Trusted Publishing** (no API tokens), TestPyPI first.
- Semantic versioning, `CHANGELOG.md`, docs site.

## 9. Phased roadmap

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 0. Decisions | Answers to Section 10, final name, license | Signed-off PLAN v1.0 |
| 1. Contract spec | `spec/` JSON Schema, header grammar, 10+ fixtures | Spec reviewed; fixtures cover all input/output types |
| 2. R core | contract parser, mock + 1 real engine, runner, results | `R CMD check` clean; ≥ 90% coverage on core |
| 3. R Shiny | modules, auto-UI, log panel, ExtendedTask, `sas_app()` | `testServer()` suite; demo app on mock + real SAS |
| 4. Python core + Shiny | parity port against the same fixtures | Shared fixture suite passes in both |
| 5. Docs | vignettes, pkgdown, Python docs, examples gallery | New user runs demo in < 10 min |
| 6. Hardening | security review (injection), concurrency, sessions | Threat model + tests |
| 7. Release | CRAN submission (R), PyPI release (Python) | Accepted on CRAN; published on PyPI |

## 10. Open decisions

See the questions issued with this plan; answers will be recorded here.

## 11. Prior art to study and differentiate from

- `sasr` (CRAN, insightsengineering): SAS session + code execution from R via saspy/reticulate.
- `sasquatch` (rOpenSci): SAS in Quarto via saspy/reticulate.
- `saspy`, `swat` (SAS Institute): official Python clients for SAS 9.4/Viya and CAS.
- PharmaSUG 2024 AP-212 "Execute SAS Procs from Shiny Application".

SAShiny's differentiation: **a declarative contract that turns an unchanged SAS program into a Shiny server,
with auto-generated, module-based UI, in both R and Python.**

---
Trademarks: SAS is a registered trademark of SAS Institute Inc. Shiny is a registered trademark of
Posit Software, PBC. This project is not affiliated with or endorsed by either company.
