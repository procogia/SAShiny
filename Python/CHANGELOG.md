# Changelog

All notable changes to the Python library are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
