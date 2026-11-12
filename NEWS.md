# SAShiny (development version)

## Demo

* The demo app has a fourth tab, **Forecasting** (`examples/forecasting`):
  monthly prescription demand forecasting with ARIMA and seasonal ARIMA
  (`PROC ARIMA`, SAS/ETS), with holdout comparison of eight candidate models,
  a user-selectable final model, diagnostics and forecasts with prediction
  intervals.

# SAShiny 0.1.3

## Shiny module layout

* Output cards no longer shrink to fit the viewport. The sidebar layout is no
  longer fillable and each card renders at its natural height, so tables,
  charts and the log scroll with the page instead of inside a thin strip
  (issue #26).

# SAShiny 0.1.2

## Client-side chart output

* New `chart` output type (spec §8.5): SAS produces only the data (collected
  like a `table`), and the Shiny module renders the plot client-side. A
  declarative `spec` (kind + column mappings, optional `backend`) or a
  per-language `render` callback drives the chart. Backends: `ggplot2`, base R
  graphics and `plotly` in R; `plotnine`, `matplotlib` and `plotly` in Python.
  The existing `plot` (ODS graphics) type is unchanged.

## Chart backend fixes

* `sas_program_server(render = )` now gives each `chart` output its own
  callback. Previously every chart received the callback of the contract's
  last output id (usually none), so callback-drawn charts showed "Could not
  render this chart: chart has no spec and no render callback".
* The `ggplot2` (default) and `plotly` backends now build a data frame from the
  collected value before plotting; they previously failed for every chart
  kind (#18).
* Spec column names (`x`, `y`, `color`, `fill`, `facet`) are resolved
  case-insensitively to the collected SAS column names, as spec §8.5
  requires, for every backend. A histogram ignores `y`. SAS missing values
  become `NA`.
* The `base` backend now draws on its own null device, so charts render when
  R runs headless (Rscript, Shiny Server, Posit Connect, Docker). It
  previously produced no image outside RStudio (#20). Rendering no longer
  leaves an `Rplots.pdf` device open.
* In the Shiny module, `plotly` charts are shown as interactive plotly
  widgets, so no static-image export (`kaleido`) is needed. `ggplot2` and base
  charts are drawn at 1200 x 900 pixels (8 x 6 in at 150 dpi).
* When a chart cannot be rendered, the module now shows the reason and logs
  it with `message()` (#21).

# SAShiny 0.1.1

## Wrapper quoting fix

* SAS-literal values (quoted/dquoted text/choice, numeric, date, multichoice,
  dataset, and validated bare names) are now emitted without `%superq`, so
  `WHERE` clauses work on real SAS 9.4 (issue #16). Only `raw` text/choice
  values keep `%superq`, because those are unquoted and could contain live `&`
  or `%`. This fixes the syntax error that broke all three example programs on
  live SAS.

## SAS OnDemand for Academics fixes

* The saspy engine submits `options notes;` once per new SAS session (spec
  6.1). ODA starts sessions with `NONOTES`, which removed the `NOTE:` sentinels,
  so every run was reported as an error and the program log was empty.
* The SAS version is read from the `SXVER=` output line, not the source echo,
  which servers like ODA include in the log (it was reported as `&sysvlong;`).

## Live engine fixes

* Dataset uploads no longer fail with `ValueError: call stack is not deep
  enough` (issue #17). `reticulate::r_to_py()` gave uploaded data frames a
  string `Index`, which caused saspy's `dataframe2sasdata()` to call
  `warnings.warn()` with no Python frame on the stack; the index is now reset
  to a `RangeIndex` and `df2sd` is invoked through a Python wrapper function.
* Reading an empty or reticulate-converted result table no longer crashes with
  "missing value where TRUE/FALSE needed" when `sd2df` returns a 0-row table
  as a list of empty lists (where `nrow()` is `NULL`) or a multi-element cell
  (issue #17).

# SAShiny 0.1.0

## Live demo tests

* Before starting saspy, the engine now checks that Java is available for IOM
  connections and that `~/.authinfo` has an entry for the profile's `authkey`.
  Without the second check saspy would prompt for credentials on stdin, which
  hangs a Shiny app.
* A live test suite runs the demo scenarios (`examples/demo-scenarios.yml`) on
  real SAS when `SASHINY_LIVE=1`, and offline tests check the scenarios and any
  committed recordings.

## Live engine and result collection

* The saspy engine now runs end to end. It writes a saspy configuration file
  from the connection settings, keeps one SAS session across runs (an
  environment), and starts a fresh session after a failure.
* Dataset inputs are uploaded with `df2sd` (spec section 7) from a user file, a
  Shiny `fileInput` value or the contract's `sample`. CSV, xlsx (`openxlsx`),
  xpt and sas7bdat (`haven`) are read and converted as specified.
* Every output type is collected (spec section 8.2): raw or SAS-formatted
  tables with column metadata and row counts, plots, HTML, scoped logs, and
  csv/xlsx (`openxlsx`)/xpt (`haven`)/sas7bdat/rtf/pdf downloads. A failing
  output becomes `list(error = )` without affecting the others
  (`metadata$collect_errors`).
* `choices_from` inputs read their choices from SAS at session start (spec
  section 6.4); new generic `sas_engine_choices()`.
* Recordings (spec section 8.3): `sas_connect(..., record_to = )` saves each run
  and `sas_engine_mock()` replays it. The key is shared with the Python library,
  so recordings made in either language replay in both.
* `sas_engine_run()` is now an S3 generic with methods for the mock engine, the
  saspy engine and pools (previously every engine ran the mock code path). New
  generic `sas_engine_close()`.
* `sas_pool()` accepts an engine factory, so each pooled session has its own
  SAS session; it closes discarded sessions and keeps sessions after input
  validation errors.
* The Shiny module renders one card per contract output, applies contract
  defaults and `ui$order`, converts Shiny values to the contract JSON form,
  supports uploads with a "use the sample file" toggle, and offers downloads.
* The demo app routes runs to ODA, Viya or SAS 9.4 and falls back to the
  offline recordings when live SAS is unavailable.
* Run ids come from `openssl::rand_bytes()`, leaving the caller's random
  number stream untouched.

## Earlier in 0.1.0

* Fixed the R demo app (`inst/examples/demo/app.R`): it now attaches SAShiny,
  locates `examples/` from any working directory, and uses a `bslib` sidebar.
* `sas_wrapper_code()` now strips a UTF-8 BOM at the byte level and marks the
  program text as UTF-8, so output no longer depends on the session locale
  (spec section 6.3).
* Result metadata `contract_sha256` is now the SHA-256 of the contract YAML
  bytes, as spec section 8 requires (previously it hashed the SAS program).
* Made tests robust when Suggests packages are unavailable and converted the
  getting-started vignette to `knitr`'s native HTML format.
* Added the contract loader and validator (`sas_contract()`, `sas_validate()`)
  implementing spec sections 1-3 (E000, S001-S016).
* Added value validation and rendering (`sas_render_values()`) implementing
  spec sections 4-5 (V001-V014).
* Added the generated SAS wrapper (`sas_reset_code()`, `sas_wrapper_code()`)
  implementing spec section 6.
* Added advisory lint (`sashiny_lint()`) as a stub for spec section 10.
* Added the mock engine (`sas_engine_mock()`) and result object
  (`sashiny_result()`).
* Added the saspy engine (`sas_engine_saspy()`, `sas_connect()`) with
  selectable connection profiles (ODA, Viya, SAS 9.4).
* Added the bounded session pool (`sas_pool()`).
* Added the runner (`sas_run()`) and app helper (`sas_app()`).
* Added the Shiny modules (`sas_program_ui()`, `sas_program_server()`) with
  auto-generated UI and custom override.
