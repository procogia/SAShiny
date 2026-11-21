# Proposal: deployment split and core dependency review

Refs #130 H6/H7. **Proposal only; no code moves in this PR.** Recommendation: **Option A (keep as is)**,
as agreed during planning, with the dependency table in section 3 left for Mehar to decide.

## 1. Inventory

About 2,160 of the 7,712 lines in `R/R/` deploy the *interface* (a Shiny or Streamlit app), not SAS.

### R

| File | Lines | Exported functions | Packages used (`pkg::`) | Tests |
|---|---:|---|---|---|
| `deploy.R` | 373 | `sas_deploy()`, `sas_deploy_targets()`, `sas_deploy_doctor()` | `shiny`, `remotes`, `utils` | `test-deploy.R` (24) |
| `deploy-addin.R` | 104 | `sas_deploy_addin()` | `shiny`, `rstudioapi`, `stats` | `test-deploy.R` |
| `publish.R` | 283 | `sas_publish()`, `sas_publish_addin()` | `rsconnect`, `rstudioapi`, `shiny`, `utils` | `test-publish.R` (5) |
| `targets-azure.R` | 395 | internal (registered target) | none; writes Bicep text | `test-deploy.R` |
| `targets-aws.R` | 440 | internal | none; writes CloudFormation text | `test-deploy.R` |
| `targets-snowflake.R` | 304 | internal | none; writes spec/SQL text | `test-deploy.R` |
| `targets-posit-snowflake.R` | 216 | internal | `rsconnect`, `stats` | `test-deploy.R` |
| `targets-databricks.R` | 22 | internal (Python-only stub that errors) | none | `test-deploy.R` |
| `targets-streamlit.R` | 23 | internal (Python-only stub that errors) | none | `test-deploy.R` |

### Python

| Module | Lines | Public API | Extras | Tests |
|---|---:|---|---|---|
| `deploy.py` | 323 | `sashiny.deploy` (lazy), `deploy()`, `targets()`, `doctor()` | none | `test_deploy.py` (26) |
| `publish.py` | 137 | `sashiny.publish()` | `connect` (`rsconnect-python`) | `test_publish.py` (4) |
| `targets/*.py` | 1,780 | internal (registered targets) | none | `test_deploy.py` |
| `streamlit_app.py` | 446 | Streamlit front end (spec §6.9) | `streamlit` | `test_streamlit_app.py` (11) |

CI: `deploy.yml` lints the generated artifacts (Bicep, CloudFormation, Dockerfile, SQL) and needs no
cloud credentials. No target calls a cloud API during checks; `apply = TRUE` / `apply=True` shells
out to the vendor CLI only when a user asks.

## 2. Options

| | A. Keep as is | B. Companion package (`SAShiny.deploy` / `sashiny-deploy`) | C. Posit Connect in core, the rest in the companion |
|---|---|---|---|
| CRAN review surface | Largest: about 2,200 extra lines and 6 exports to review | Smallest core; the companion is a second submission | Core keeps `sas_publish()` (283 lines); the companion takes the rest |
| Install footprint | Unchanged: the targets need no extra packages (they write text); `rsconnect`/`remotes`/`rstudioapi` stay in Suggests | Same for core; users who deploy install a second package | As B |
| User migration | None | `sas_deploy()` moves; core keeps a shim that calls the companion through `rlang::check_installed()`, warning via `lifecycle::deprecate_soft()` | As B for `sas_deploy*()`; `sas_publish()` unchanged |
| CI changes | None | A second `R CMD check` and `uv build`; spec fixtures under `spec/fixtures/deploy` move with the companion; lockstep version check covers 4 packages | As B |
| Release coordination | One package per language | Two per language, which conflicts with lockstep versions (prompt 10) unless the companion is included | As B |

**Why A for now.** The deployment code has no hard dependencies, is fully exercised without network
access, and only writes files. Splitting adds a second CRAN submission while 0.2.0 is still in the
6-week window, and a second PyPI project, for no reduction in install size. Revisit B or C if a
target needs a hard dependency (for example a cloud SDK) or if CRAN reviewers object to the size.

## 3. Core dependency table (R)

The review questioned keeping `shiny`, `bslib`, `promises`, `later` and `callr` in Suggests for a
package named SAShiny. Since then `callr` moved to Imports (persistent workers, prompt 1). The
repository rule is "keep hard Imports minimal; optional backends in Suggests". Moving the Shiny stack
to Imports conflicts with that rule, so **Mehar decides**.

| Package | Where it is required | Without it | Recommendation |
|---|---|---|---|
| `callr` | `worker.R`: one persistent R session per saspy engine | — | **Imports** (done) |
| `shiny` | `app.R`, `mod-program.R`, addins, worker promises | No app or module; contracts, values, wrapper and `sas_run()` still work | **Imports** suggested (the package name promises Shiny), *conflicts with the rule* |
| `promises` | `mod-program.R`, `worker.R`, `pool.R`, `choices-cache.R` | Runs block the app process | Imports *with* `shiny`, else Suggests |
| `later` | `worker.R`, `pool.R` polling | Same as `promises` | Imports *with* `shiny`, else Suggests |
| `bslib` | Sidebar layout and task button | Falls back to `sidebarLayout` | Suggests |
| `htmltools` | Paired-chart toggle dependency | Installed with `shiny` | Suggests (comes with `shiny`) |
| `ggplot2`, `plotly` | Chart backends (spec §8.5) | Chart outputs report a collection error | Suggests |
| `haven`, `openxlsx` | `xpt`/`sas7bdat`/`xlsx` uploads and downloads | Those formats report V014 | Suggests |
| `reticulate` | saspy bridge for live runs | No live runs (the purpose of the package) | Suggests: CRAN checks have no Python, and `check_installed()` explains the gap |
| `rsconnect`, `rstudioapi`, `remotes` | Publishing and addins | `sas_publish()` / addins stop with an install hint | Suggests |
| `knitr`, `rmarkdown`, `testthat`, `withr`, `rlang` | Vignettes and tests | — | Suggests |

Python is already split by extras (`saspy`, `shiny`, `connect`, `upload`, `plotnine`, `matplotlib`,
`plotly`, `streamlit`); core depends only on `jsonschema` and `pyyaml`. The matching question there is
whether `shiny` becomes a core dependency; the same trade-off applies.

## 4. Migration plan (if B or C is chosen later)

1. Create `R-deploy/` and `Python-deploy/` package roots in this repository, with the deployment
   files moved unchanged and their tests and `spec/fixtures/deploy` alongside.
2. In core, keep `sas_deploy()`, `sas_deploy_targets()`, `sas_deploy_doctor()` and
   `sas_deploy_addin()` (and `sashiny.deploy`) as shims for two minor releases: each calls
   `rlang::check_installed("SAShiny.deploy")` / imports `sashiny_deploy`, emits
   `lifecycle::deprecate_soft()` / `DeprecationWarning`, and forwards its arguments.
3. Under C, `sas_publish()` and `sashiny.publish()` stay in core with no change.
4. Extend the lockstep version check (prompt 10) to the companion packages; release them together.
5. Remove the shims after two minor releases, with NEWS/CHANGELOG entries at each step.