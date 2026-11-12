# Daytona test report — merged `main` (2026-11-12)

Validation of the merged `main` (`ed15ee2`) on a clean Daytona sandbox (Debian 13
"trixie", x86_64), to confirm the merged output is green before the team
continues testing. The local development machine is Windows, so this also
validates cross-platform behaviour.

## Sandbox

- Image: Daytona default (Debian 13), Python 3.14.10, uv 0.9.26, git 2.56.0.
- Installed for the run: R 4.5.0, OpenJDK 21, and the R system libraries
  (`libv8-dev`, `libsass-dev`, `libcurl4-openssl-dev`, `libssl-dev`,
  `libxml2-dev`, `libfontconfig1-dev`, `libfreetype6-dev`, `libpng-dev`,
  `libtiff5-dev`, `libjpeg-dev`).
- Repo cloned at `ed15ee2` (the merged `main`).

## Results

| Check | Result |
|---|---|
| Spec gate (`spec/tools/check_spec.py`) | 120 passed, 0 failed |
| Python `ruff check` | clean |
| Python `ruff format --check` | clean |
| Python `mypy --strict` (all extras installed) | no issues |
| Python `pytest` (all extras: plotnine, matplotlib, plotly, shiny, saspy, upload) | 218 passed, 29 skipped |
| R testthat suite (ggplot2 + plotly installed) | 0 failed, 462 passed, 18 skipped |
| Demo app smoke test (Python, Offline profile) | serves HTTP 200, title "SAShiny demo" |

The skipped tests are the expected ones: live-SAS tests (opt-in via
`SASHINY_LIVE=1`) and demo-scenario replay tests (no recordings in
`examples/recordings/` yet). The single R warning is the pre-existing xlsx
zip-extraction warning, unrelated to the merged changes.

## Demo app smoke test

The Python demo app (`Python/examples/demo/app.py`) was started with the
Offline profile (the default) and served `HTTP 200` with the title
"SAShiny demo" on port 8000. The app starts and serves correctly; full offline
replay is not exercised because `examples/recordings/` is empty (recordings
require a live SAS run, tracked in issue #11).

Docker was not available inside the sandbox (Daytona sandboxes are themselves
containers), so the `Dockerfile` image was not built here. The demo app was
smoke-tested directly instead, which exercises the same code path.

## Conclusion

The merged `main` is green on a clean Linux sandbox: spec, Python (lint + type
+ tests with all chart backends) and R (full testthat suite) all pass, and the
demo app serves. No code changes were needed.