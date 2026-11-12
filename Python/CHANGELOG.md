# Changelog

All notable changes to the Python library are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
