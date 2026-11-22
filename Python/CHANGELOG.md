# Changelog

All notable changes to the Python library are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Replay and registered engines (spec §6.6, spec release 1.7). `program_server`, `app`, `run`
  and `Pool` now also accept:
  - `sashiny.replay(recordings_dir)` (`ReplayEngine`), which replays recordings (§8.3) of runs
    made on a live, licensed SAS system. A recording is replayed only when it carries its
    `sas_version` (`&SYSVLONG`), `recorded_at` and the SHA-256 of the contract and program it
    was made from, both matching the files on disk. Otherwise the run is an error result with
    `metadata["recording"] == "refused"` and the reason in `metadata["engine_error"]`; inputs
    never recorded give `"missing"`. A replayed result has `metadata["recording"] ==
    "replayed"` and a `metadata["notice"]` such as "Replayed from 9.04.01M0P061913, recorded
    2015-07-30T12:00:00Z.", which the module's status text shows.
  - instances of an `Engine` subclass registered with
    `sashiny.register_engine(cls, license_ack=True, description=...)`. The registrant
    acknowledges that the engine runs every program on a live, licensed SAS system;
    `SASHINY_LICENSE_ACK` does not register an engine. `registered_engines()` and
    `unregister_engine()` list and remove registrations.
- `sashiny.engine_result()` builds a result with the §8.4 metadata for a registered engine, and
  `sashiny.record()` writes a live or registered engine's result as a recording. It refuses
  results without a SAS version, replays, cache hits and results from another contract or
  program. The recording key is unchanged, so existing recordings keep their names.
- `values` in `program_server()` can now supply a dataset input: pass a pandas `DataFrame` and it
  replaces the upload control. It is written as CSV in a canonical form (spec §7.1) and checked
  like an uploaded file, so a missing declared column is `V014`. `run(uploads=)` accepts
  DataFrames too. The same data frame gives the same CSV bytes in R and Python, so result-cache
  and recording keys agree. This lets a parent app pass its filtered data to SAS.
- Lint `L006` (spec §10): with `run.entry: macro`, an input macro name that the entry macro has
  no parameter for. SAS rejects such a call (`The keyword parameter ... was not defined with the
  macro`). A `/ parmbuff` macro is not checked. Same code, message and fixtures as R (#163).

### Changed

- A value supplied through `values` for a dataset input is no longer ignored: a DataFrame replaces
  the upload, `None` removes it, and anything else is `V014`.

- Contract YAML numbers follow the shared rule of spec §1.1 (the YAML 1.2 core number forms
  both languages' YAML parsers recognise), so a contract is valid in R and Python or in neither:
  `-.5`, `+.5` and `-.5E-3` are now numbers; `1_000`, `017`, `0b101` and `1:30` are now strings
  (`E000` where a number is expected) instead of 1000, 15, 5 and 90 (#155).
- Run timestamps (`started_at`, `ended_at`, a recording's `recorded_at`) are written as
  `YYYY-MM-DDTHH:MM:SSZ` (UTC, whole seconds), the form R writes and `cached_at` already used
  (spec §8.4). Results with `+00:00` timestamps are still read, also on Python 3.10. Every engine
  (mock, saspy, PROC PYTHON, pool) reports the package version as `engine_version` instead of
  `"0.1.0"`, as R does (#156).

### Fixed

- The General (`cars_explorer.sas`) and AML (`cash_aggregation_tuning.sas`) example programs set
  their standalone defaults inside a macro instead of with open-code `%if`, so they run on every
  SAS 9.4 release. On 9.4M0 to M4 the open-code `%if` was an error and every output came back empty.
- `Pool` clears its `choices_from` cache when it discards a failed session (spec §6.4), as
  R does; choices from the discarded SAS session were offered and validated against (#152).
- `split_log` (the `log` output, `Result.log_frame()`, failure reasons) strips only ASCII
  trailing whitespace (spec §8.1, §8.2), as R does; a trailing U+00A0, U+2003, U+3000 or U+0085
  now stays (#154).
- A one-column CSV upload, or a one-column DataFrame for a dataset input, keeps its rows whose
  value is missing or `""`: with a single header field every line after the header is a row, so
  an empty line is a missing value (spec §7). They were dropped as blank lines, so SAS
  got fewer rows (#164).
- `run(contract, engine)` without `values` uses the contract's defaults, as its docs say: every
  input `values` does not supply takes its `default`, with `"today"` resolved against `today`, so
  a scripted run submits what a first click of Run does (spec §6.12). It passed no values, so
  every required input was `V001`. A supplied `None` still makes an input absent (#162).

R/Python parity pass (spec release 1.5, `docs/parity.md`).

### Changed (breaking)

- `publish(name=)` is the content name, as in R's `sas_publish()` (it defaults to the
  directory name). The rsconnect server nickname moved to the new `server=` argument.
  `rsconnect-python` derives the content name from the title, so with both `name` and
  `title` the content name follows the title, with a `UserWarning`.
- `metadata["engine_error"]` holds the message only, without the exception class name.
- `parse_profile()` raises `DeployError` (still a `ValueError`); `PoolExhausted` is an
  `EngineError`.

### Added

- `program_server(render=)`: the R argument name for chart render callbacks
  (`chart_render=` still works).
- `render_values()` defaults `today` to today and `render_chart()` defaults `spec` to
  `None`, as in R.

### Fixed

- Declared `character` upload columns turn native cells into the spec §7.1 text, as R
  does: `1`/`0` for booleans (was `True`/`False`), `%.17g` numbers and ISO dates
  (spec §7, step 3).
- `SaspyEngine.close()` clears the `choices_from` cache too (spec §6.4).
- Upload blank detection and table `label`/`format` strip ASCII blanks only, as in R (spec §8.1).
- `""` for a `multichoice` or `daterange` input is `V002` (spec §4), and an integer too
  large for a double is `V003` instead of an `OverflowError`.
- A second run on a busy `SaspyEngine` waits up to 30 s, then returns
  `engine busy: another run is in progress` (it used to cancel the first run).
- `connect(backend, region=...)` rejects connection arguments next to a backend, as in R.
- `connect_from_env()` treats an empty `SASHINY_ODA_REGION` or `SASHINY_SAS94_PORT` as unset.
- An empty `cached_choices` is used instead of being re-queried.
- Lint uses ASCII word boundaries, as R's PCRE does.
- `default_module_id()` splits on `/` and `\` on every platform and strips every combining
  mark (Unicode category M).
- matplotlib honours `xlab`/`ylab` and the faceted `subtitle`, and refuses `color`/`fill`
  mappings it cannot draw; plotly refuses `color` and `fill` together (spec §8.5).

## [0.3.1] - 2026-11-20

### Deprecated

- `sashiny.run()` takes the engine second: `run(contract, engine, values=None)`. The old order
  still works and emits a `DeprecationWarning` (#130). New `sashiny.close()` closes engines
  and pools.

### Added

- In-session engine for PROC PYTHON (spec §6.5, §6.6; #128):
  `sashiny.connect_in_session(SAS, license_ack=..., own_session=...)` returns a
  `ProcPythonEngine` that runs contracts through the `SAS` callback object inside a
  SAS Viya or SAS 9.4M9+ job (batch only, no pool). The log and listing are captured
  with `PROC PRINTTO` and `ODS HTML5` files in WORK. `reset_work` is refused unless
  `own_session=True`. A timeout stops waiting and disables the engine; the scheduler
  ends the job. Live parity is an opt-in QA check (`tests/live/procpython/probe.sas`).
- Opt-in result cache (spec §6.11): `run.cache: true` and `run.cache_ttl_seconds`
  (default 3600). Identical `success`/`warning` runs are reused with
  `metadata["cache_hit"]` and `metadata["cached_at"]`. **Off by default.** The new
  `sashiny.result_cache` module holds a per-process LRU of 100 results;
  `result_cache.set_store()` plugs in another store. Covers `run()`, the Shiny
  module and the Streamlit front end.
- `program_server()` gains `values`, a reactive of input values that other Shiny
  code uses to drive a contract's inputs (spec §6.10), plus `hide_inputs` and
  `debounce_ms` (default 500) for `ui.auto_run`. `modules.merge_values()` merges
  them over UI values. See `examples/parent-filter/`.
- Lockstep versions with the R package (spec §11): both are 0.3.1. New
  `sashiny.info()` returns the library version, the spec release (`1.4`) and the
  contract version; CI fails when the R and Python versions or spec releases differ.
- `choices_from` lists load once per app and contract, cached for the new
  `run.choices_ttl_seconds` (default 3600), and load in the background in a Shiny app
  (spec §6.4, #130).
- Exception hierarchy (#130): `SashinyError` with `ContractError`, `ValuesError`, `EngineError`,
  `LicenseError`, `UploadError`, `DeployError` and `RunError`, each also a subclass of the
  built-in it replaces. `validate(..., raise_error=True)`, `Result.check()` and a readable
  `Result.__repr__`, all matching R.
- `Result.table(id)`, `Result.log_frame()` and `Result.frames()` return pandas DataFrames
  (spec §8.7, #130). New extra `sashiny[frames]`; the core still imports without pandas.

### Fixed

- The `container` deployment image now builds and runs (spec §6.8). The Python image is based on
  `python:3.12-slim-bookworm`, because current `python:3.12-slim` (Debian trixie) has no Java 17.
  The R image installs R packages as Linux binaries from its base image's repository instead of
  compiling them from CRAN source, and adds `libpython3-dev` (for reticulate) and `ggplot2` (for
  charts). Its build now fails when a package is missing. The Azure, AWS and Snowflake container
  targets share this Dockerfile and get the same fixes.

## [0.3.0] - 2026-11-17

### Added

- Deployment targets (spec §6.8): `sashiny.deploy.deploy()` writes deployment artifacts for an
  app directory and `sashiny.deploy.targets()` lists them. The first target is `container` (a
  non-root `Dockerfile` with a health check; Java 17 only for IOM profiles). Generating never
  touches the network; `apply=True` and `sashiny.deploy.doctor()` run platform tools through a
  replaceable runner. Credential files are never bundled; generated files hold secret names only.
- Deployment target `azure_container_apps` (spec §6.8.1): a Bicep template (sticky sessions,
  WebSockets, managed identity, Key Vault secret references, optional VNet subnet), a parameters
  file and a deployment guide.
- Deployment target `aws_ecs_express` (spec §6.8.2): a CloudFormation template for ECS on Fargate
  behind an Application Load Balancer, with cookie stickiness, a one-hour idle timeout for
  WebSockets, Secrets Manager secret references and SAS egress rules, plus a deployment guide.
- Deployment target `snowflake_spcs` (spec §6.8.3): a Snowpark Container Services specification,
  setup SQL (image repository, compute pool, egress network rule, external access integration), a
  placeholder-only secret script, service SQL and a deployment guide.
- Deployment target `posit_snowflake` (spec §6.8.4): publishes to Posit Connect in the Posit Team
  Native App with `sashiny.publish()`, and writes the egress SQL that lets Connect reach SAS
  (public or private connectivity).
- Streamlit front end (spec §6.9): `sashiny.streamlit_app.streamlit_app` renders contracts as a
  Streamlit app with the same validation, wrapper and engines; runs in a background thread. New
  extra `sashiny[streamlit]`. Python only (no R equivalent).
- Deployment target `streamlit_snowflake` (spec §6.8.5): Streamlit in Snowflake on the container
  runtime, for SAS Viya (http) profiles; entry point, `pyproject.toml`, setup/secret/streamlit SQL
  and a deployment guide.
- Deployment target `databricks_apps` (spec §6.8.6): Shiny for Python on Databricks Apps for SAS
  Viya (http) profiles: `app.yaml` (`DATABRICKS_APP_PORT`, secret resources via `valueFrom`),
  pinned `requirements.txt`, the `apps create` JSON and a deployment guide. R apps are rejected.
- Deployment docs (`docs/deployment.md`), a manual verification checklist
  (`docs/deploy-verification.md`) and a CI job that generates every target and lints the output
  (hadolint, `az bicep build`, cfn-lint, yamllint).
- `sashiny.parse_profile()` / `Profile` validate a connection profile and derive its egress
  endpoints, Java need and runtime variables; `sashiny.connect_from_env()` builds a deployed
  app's engine from those variables.
- Bundles skip `.git`, `__pycache__`, `rsconnect` and similar folders at any depth and list files
  in byte order (spec §6.8; also for `sashiny.publish`).
- Paired outputs (spec §2.2 and §8.6) show the original SAS graph and the SAShiny chart in one
  card, with a toggle in the browser. Declare one with `sas_plot: <k>` on a `chart` output, or
  a `chart:` block on a `plot` output (which needs `select`). Each card has its own
  toggle, and a module toggle switches them all, with no server round trip.
- `program_server` and `sashiny.app` take `chart_view` (`"sashiny"` by default, `"sas"`,
  or a dict per output) and `chart_toggle` (`True` by default; `False` hides the toggles).
- Each part of a paired output is collected on its own, so one failing does not hide the other.

### Fixed

- With `entry: macro`, each value is now written into the macro call with only commas,
  semicolons, `&`, `%` and unmatched quotes or parentheses masked (spec §6.3), instead of
  `NAME=%bquote(&NAME)`. The fully macro-quoted values broke `WHERE` clauses such as
  `where product = &product` and names built from a value such as `l&conf_level`, so the
  Pharma and Forecasting demos failed on live SAS.
- The disabled download placeholder shown before a run no longer reuses the output's id, which
  made Shiny report a shared input/output id.
- The demo Docker image defaults to the `oda` profile (the removed `offline` profile stopped the
  app from starting) and installs the `upload` and `plotnine` extras the demo needs (plotnine
  is the default chart backend). The documented demo run commands add `--extra plotnine`.
- The Run button is a task button (#108): it shows "Running..." and stays disabled until the
  run finishes, so it is clear that a run is in progress.

## [0.2.0]

### Changed (breaking)

- Programs run only on a live SAS 9.4, SAS Viya or SAS OnDemand for Academics system (spec
  §6.6). `SaspyEngine` rejects other saspy configurations (local COM, local STDIO, unknown
  methods).
- A run returns an error ("SAS licence not acknowledged") unless `license_ack=True` or
  `SASHINY_LICENSE_ACK=true` is set. You are responsible for your SAS licence.
- `MockEngine`, `save_recording`, `load_recording` and the `record_to` /
  `session_factory` arguments were removed from the public API. The mock is now an internal
  test fixture, so logs and results cannot be supplied by hand.
- `sashiny.app`, `program_server`, `sashiny.run` and `Pool` accept only `connect()` /
  `SaspyEngine` engines and pools.

### Added

- `sashiny.publish()` deploys an app to Posit Connect with `rsconnect-python` (extra
  `sashiny[connect]`, spec §6.7). Credential files are never bundled.
- `sashiny.app(..., publish=True)` adds an opt-in "Publish" tab, which is hidden on Connect.
- Live engines pass `SASHINY_SAS_USER` / `SASHINY_SAS_PASSWORD` to saspy when both are set.

## [0.1.7] - 2026-11-14

### Added
- `sashiny.json_values()` parses a JSON object of input values, the counterpart
  of R's `sas_json_values()` (spec §4, #102).

### Fixed
- A matplotlib `box` chart with `color` no longer passes the removed
  `Axes.boxplot(labels=)` keyword, so it works on matplotlib 3.9 and later (#100).
- In the Shiny module, an upload over `max_size_mb` is shown as a V014 error in
  the status card instead of raising in the Run effect (spec §7, #101).

## [0.1.6]

### Added
- Advisory lint (`sashiny.lint`) reporting L001–L005 program-vs-contract
  consistency findings (spec §10): an injected macro assigned outside a
  `%symexist` guard, an injected macro never referenced, a `table`/`download`
  `from` dataset never created, more than one rtf/pdf download, and
  `entry: macro` without a matching `%macro` (#28).

### Fixed
- `extract_plots` now rejects `select < 1` with a clean `ValueError` instead of
  returning the wrong plot or leaking `IndexError` (#29).
- R/Python parity in cell and upload normalisation: character cells strip ASCII
  whitespace only (not Unicode), a literal `NA` in a date column is unparseable,
  a whitespace-only non-CSV numeric cell is missing, and character columns drop
  the `.0` of integer-valued floats (#30–#33).
- Contract/value validation parity: impossible calendar-date bounds return
  `S003` instead of raising, `^`/`$` inside character classes are allowed, text
  `pattern` uses ASCII `\d`/`\w`/`\s` semantics, and choice values are no longer
  whitespace-trimmed (spec §3.2, §3.3, §4; #38–#40, #46).
- Upload parsing: duplicate CSV headers resolve to `x`, `x_2`; XLSX reads with
  `keep_default_na=False` preserve literal `NA` and leading zeros; date columns
  require the exact `YYYY-MM-DD` shape (#41–#43).
- Engine and pool lifecycle: failed SAS sessions are closed before their
  reference is dropped, the pool warms `min_size` sessions and discards a
  session whose `engine.run` raises, and `run.timeout_seconds` is enforced
  (#34–#37, #44–#45).

## [0.1.5]

### Added
- A fourth demo track, **Forecasting** (`examples/forecasting`): monthly
  prescription demand forecasting with ARIMA and seasonal ARIMA (`PROC ARIMA`,
  SAS/ETS). It compares eight candidate models on a holdout window, lets the user
  pick the final model or set its orders, and shows diagnostics and forecasts
  with prediction intervals. The simulated sample data come from a reproducible
  generator (`generate_rx_data.py`). The demo app, demo scenarios and live tests
  include the new track.

## [0.1.4]

### Fixed
- Output cards in the Shiny module no longer shrink to fit the viewport. The
  sidebar layout is no longer fillable and each card renders at its natural
  height, so tables, charts and the log scroll with the page instead of inside
  a thin strip (#26).

## [0.1.3]

### Fixed
- The `plotnine` (default) and `plotly` chart backends now build a
  `pandas.DataFrame` from the collected value before plotting; in 0.1.2 they
  failed for every chart kind (#19).
- Spec column names (`x`, `y`, `color`, `fill`, `facet`) are resolved
  case-insensitively to the collected SAS column names, as spec §8.5 requires,
  for every backend. A histogram ignores `y`. SAS missing values are `NaN`.
- `matplotlib` charts no longer fail on SAS missing values, group box plots by
  `x`, and are no longer registered with pyplot, so a long-running server does
  not accumulate figures.

### Changed
- In the Shiny module, `plotly` charts are shown as interactive plotly charts,
  using the plotly.js bundled with the `plotly` package (no `kaleido`, Chrome
  or CDN needed). `plotnine` and `matplotlib` charts are drawn at 1200 x 900
  pixels (8 x 6 in at 150 dpi). Render errors are logged.
- The `plotly` extra now also installs `pandas`.

## [0.1.2]

### Added
- Client-side `chart` output type (spec §8.5): SAS produces only the data
  (collected like a `table`), and the Shiny module renders the plot client-side.
  A declarative `spec` (kind + column mappings, optional `backend`) or a
  per-language `render` callback drives the chart. Backends: `plotnine`,
  `matplotlib` and `plotly`. The existing `plot` (ODS graphics) type is
  unchanged.

## [0.1.1]

### Fixed
- `import sashiny` no longer requires the optional `shiny` extra. `app` and
  `modules` are imported lazily, so the core package works with only its
  declared dependencies.
- SAS-literal values (quoted/dquoted text/choice, numeric, date, multichoice,
  dataset, validated bare) are emitted without `%superq`, so `WHERE` clauses
  work on real SAS 9.4 (issue #16). Only `raw` text/choice keeps `%superq`.

### Fixed (SAS OnDemand for Academics)
- `SaspyEngine` submits `options notes;` once per new SAS session (spec 6.1).
  ODA starts sessions with `NONOTES`, which removed the `NOTE:` sentinels, so
  every run was reported as an error and the program log was empty.
- The SAS version is read from the `SXVER=` output line, not the source echo,
  which servers like ODA include in the log (it was reported as `&sysvlong;`).

## [0.1.0]

### Added (live demo tests)
- Before starting saspy, `SaspyEngine` checks that Java is available for IOM
  connections and that `~/.authinfo` has an entry for the profile's `authkey`
  (`sashiny.engines.saspy.preflight`). Without the second check saspy would
  prompt for credentials on stdin, which hangs a Shiny app.
- `tests/live` runs the demo scenarios (`examples/demo-scenarios.yml`) on real
  SAS when `SASHINY_LIVE=1`; offline tests check the scenarios and any
  committed recordings.

### Added (live engine and result collection)
- `SaspyEngine` runs end to end: the session starts from a generated saspy
  configuration file, persists across runs, and is restarted after a failure.
  Dataset inputs are uploaded with `df2sd` (spec §7) from a user file or the
  contract's sample. Every output type is collected per spec §8.2: tables (raw or
  SAS-formatted, with metadata and row counts), plots, HTML, scoped logs, and
  csv/xlsx/xpt/sas7bdat/rtf/pdf downloads. A failing output becomes
  `{"error": ...}` without affecting the others (`metadata.collect_errors`).
- `choices_from` inputs read their choices from SAS at session start (§6.4).
- Recordings (§8.3): `SaspyEngine(record_to=...)` / `connect(..., record_to=...)`
  save each run; `MockEngine` replays them with the shared R/Python key and
  reports `metadata.recording` as `"replayed"` or `"missing"`.
- `sashiny.collect`, `sashiny.upload` and `sashiny.recording` modules;
  `UploadFile`, `UploadError`, `load_recording` and `save_recording` exports.
- Shiny modules render one card per contract output, apply contract defaults,
  convert Shiny values to the contract JSON form, support file uploads with a
  "use the sample" toggle, and offer downloads.
- `Pool` accepts an engine factory (one SAS session per pooled session), is an
  `Engine` itself, closes discarded sessions, and keeps sessions on input
  validation errors.
- Demo app: live profiles (ODA, Viya, SAS 9.4) with automatic offline fallback.

### Changed
- Output values in `Result.outputs` are the language-neutral JSON values of spec
  §8.1 (`TableResult` and `LogLine` remain exported for compatibility).
- `uploads=` accepts file paths, `UploadFile` objects or `True` (sample).

### Fixed
- Result metadata `contract_sha256` is now the SHA-256 of the contract YAML bytes
  (spec §8); previously it hashed the SAS program. `Contract` gains a `path` field.

### Added
- Contract loader and validator (`sashiny.contract`).
- Value validation and rendering (`sashiny.values`).
- Generated SAS wrapper (`sashiny.wrapper`).
- Mock engine with record/replay and saspy engine with connection selection
  (`sashiny.engines`).
- Bounded session pool (`sashiny.pool`), runner (`sashiny.run`), result object
  (`sashiny.result`), and Shiny modules (`sashiny.modules`).
