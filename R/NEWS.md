# SAShiny (development version)

## New features

* Deployment targets (spec section 6.8). `sas_deploy()` writes deployment
  artifacts for an app directory, and `sas_deploy_targets()` lists the
  targets. The first is `container` (a non-root `Dockerfile` with a
  health check; Java 17 only for IOM profiles). Generating never touches the
  network; `apply = TRUE` and `sas_deploy_doctor()` run platform tools
  through a replaceable runner. Credential files are never bundled and
  generated files hold secret names only.
* Deployment target `azure_container_apps` (spec section 6.8.1): a Bicep
  template (sticky sessions, WebSockets, managed identity, Key Vault secret
  references, optional VNet subnet), a parameters file and a deployment guide.
* Deployment target `aws_ecs_express` (spec section 6.8.2): a CloudFormation
  template for ECS on Fargate behind an Application Load Balancer, with cookie
  stickiness, a one-hour idle timeout for WebSockets, Secrets Manager secret
  references and SAS egress rules, plus a deployment guide.
* `sas_profile()` validates a connection profile and derives its egress
  endpoints, Java need and runtime variables. `sas_connect_env()` builds a
  deployed app's engine from those variables.
* Bundles now skip `.git`, `__pycache__` and similar folders at any depth,
  and list files in byte order (spec section 6.8; also for `sas_publish()`).

# SAShiny 0.2.0

## Breaking changes

* Programs run only on a live 'SAS' 9.4, 'SAS Viya' or 'SAS OnDemand for
  Academics' system (spec section 6.6). `sas_engine_saspy()` rejects other
  saspy configurations (local COM, local STDIO, unknown methods).
* Users are responsible for their 'SAS' licence. A run returns an error
  ("SAS licence not acknowledged") unless `license_ack = TRUE`,
  `options(SAShiny.license_ack = TRUE)` or `SASHINY_LICENSE_ACK=true` is set.
* The offline mock engine and recordings are now internal test fixtures.
  `sas_engine_mock()`, `sas_engine_record()` and the `record_to` argument of
  `sas_connect()`/`sas_engine_saspy()` are removed, so logs and results can no
  longer be supplied by hand. `sas_engine_saspy()` loses `session_factory`.
* `sashiny_result()` and the backward-compatibility alias
  `sas_engine_saspy_run()` are no longer exported; use `sas_engine_run()`.
* `sas_app()`, `sas_program_server()`, `sas_run()` and `sas_pool()` accept
  only `sas_connect()`/`sas_engine_saspy()` engines and pools.

## New features

* `sas_publish()` deploys an app to Posit Connect with 'rsconnect' (spec
  section 6.7). It uses a registered account or `CONNECT_SERVER` +
  `CONNECT_API_KEY`. Credential files are never bundled. 'SAS' credentials
  reach the app as Connect environment variables (`SASHINY_SAS_USER`,
  `SASHINY_SAS_PASSWORD`) or come from an administrator-managed authinfo.
* An RStudio/Positron addin (`sas_publish_addin()`) and an opt-in "Publish"
  tab in `sas_app(publish = TRUE)`. The tab is hidden when the app runs on
  Connect.
* Live engines read `SASHINY_SAS_USER`/`SASHINY_SAS_PASSWORD` when both are
  set and pass them to saspy without writing them to a file.
* Paired outputs (spec sections 2.2 and 8.6) show the original 'SAS' graph and the
  'SAShiny' chart in one card, with a toggle in the browser. Declare one with
  `sas_plot: <k>` on a `chart` output, or a `chart:` block on a `plot` output
  (which needs `select`). Each card has its own toggle, and a module toggle
  switches them all, with no server round trip. `sas_program_server()` and
  `sas_app()` take `chart_view` (`"sashiny"` by default, `"sas"`, or a named
  list per output) and `chart_toggle` (`TRUE` by default; `FALSE` hides the
  toggles). Each part is collected on its own, so one failing does not hide the
  other. 'htmltools' is now suggested.

## Fixes

* With `entry: macro`, each value is now written into the macro call with
  only commas, semicolons, `&`, `%` and unmatched quotes or parentheses masked
  (spec section 6.3), instead of `NAME=%bquote(&NAME)`. The fully macro-quoted
  values broke `WHERE` clauses such as `where product = &product` and names
  built from a value such as `l&conf_level`, so the Pharma and Forecasting
  demos failed on live 'SAS'.
* In the Shiny module, the download button rendered after a run now uses the
  module-namespaced id, so downloads work again; before, the button stayed
  disabled. The disabled placeholder shown before a run no longer has an id.

# SAShiny 0.1.6

## New features

* `sas_json_values()` parses a JSON object of input values. An escaped
  `\u0000`, which an R string cannot hold, is rejected as V007 instead of
  silently truncating the value (spec section 4, #102).

## Fixes

* `sas_program_server()` no longer blocks other browser sessions during a run:
  in a running app a mock or saspy run executes in a 'callr' background process
  polled with 'later'. A `sas_pool()` or custom engine still runs in-process
  (#44).
* The plotly chart backend draws one subplot per `facet` level instead of
  ignoring the mapping (spec section 8.5, #72).
* A multichoice or daterange element that is a character vector of length other
  than one is V002, not flattened (spec section 2.1, #60).
* `sas_pool()` rejects a non-finite `min_size`/`max_size` such as `Inf` (#94).

* Live saspy runs work with pandas 3. Every table output was reported as
  "dataset not found", because reticulate before 1.45.0 does not convert
  pandas 3 data frames; reticulate 1.45.0 or later is now required for live
  runs, with a clear error for older versions. Dataset uploads no longer fail
  with "call stack is not deep enough", because the pandas date conversion and
  `df2sd` now run inside a Python function.

# SAShiny 0.1.5

## Lint

* `sashiny_lint()` now reports the advisory L001–L005 findings (spec §10):
  an injected macro assigned outside a `%symexist` guard, an injected macro
  never referenced, a `table`/`download` `from` dataset never created, more
  than one rtf/pdf download, and `entry: macro` without a matching `%macro`
  (#28).

## Fixes

* `.sashiny_extract_plots()` rejects `select < 1` with a clean error instead of
  returning an empty list (#29).
* R/Python parity in cell and upload normalisation: character cells strip ASCII
  whitespace only, a literal `NA` in a date column is unparseable, a
  whitespace-only non-CSV numeric cell is missing, and character columns drop
  the `.0` of integer-valued floats (#30–#33).
* Contract/value validation parity: impossible calendar-date bounds return
  `S003` instead of raising, `^`/`$` inside character classes are allowed, and
  choice values are no longer whitespace-trimmed (spec §3.2, §3.3, §4;
  #38–#40, #46).
* Engine and pool lifecycle: failed SAS sessions are closed before their
  reference is dropped and the pool warms `min_size` sessions (#35, #37).

# SAShiny 0.1.4

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
