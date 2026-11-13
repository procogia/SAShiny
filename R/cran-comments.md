## Test environments

* Local: Windows 10, R 4.6.1. `R CMD check --as-cran --no-manual`: 0 errors,
  0 warnings, 1 note. The manual was excluded because LaTeX is unavailable
  locally.
* GitHub Actions: ubuntu (R devel, release, oldrel-1, 4.1), macOS (release) and
  Windows (release): all pass.
* macOS builder, R-release (arm64): Status: OK, 0 errors, 0 warnings, 0 notes
  (0.1.4, 2026-11-12).
* win-builder, R-devel, R-release and R-oldrelease: submitted for 0.1.4 on
  2026-11-12; results arrive by email to the maintainer.
* R-hub: not re-run for 0.1.4 (the `RHUB_TOKEN` secret is not configured in the
  repository). The 0.1.1-era R-hub results (Linux, Windows, macOS, clang-asan,
  nosuggests) were `Status: OK`.

## R CMD check results

0 errors | 0 warnings | 1 note

* This is a resubmission of 0.1.1 (which was pending manual inspection). It
  adds the client-side `chart` output type (spec §8.5), fixes the Shiny module
  layout so output cards render at their natural height (issue #26), adds a
  fourth demo track (Forecasting, `examples/forecasting`), and adds the advisory
  lint (L001-L005, spec §10) plus a set of R/Python parity fixes in cell and
  upload normalisation, contract/value validation and the engine/pool lifecycle
  (issues #28-#46). The chart backends (ggplot2, base and plotly, all optional)
  are tested when installed and skipped otherwise.
* "Possibly misspelled words in DESCRIPTION: PBC". This is the correct legal
  suffix in 'Posit Software, PBC', used in the trademark statement.

## Downstream dependencies

There are currently no downstream dependencies for this package.

## Notes

* This package pairs an unmodified 'SAS' program with a 'Shiny' app. It does not
  require 'SAS', 'Python' or internet access to install or run its tests: the
  mock engine is used, and live-'SAS' tests are opt-in (`SASHINY_LIVE=1`).
* Live connections to 'SAS' have not yet been verified against a real 'SAS'
  system; the package is released as a beta.
* 'SAS' is a registered trademark of SAS Institute Inc. and 'Shiny' is a
  registered trademark of Posit Software, PBC; this package is not affiliated
  with or endorsed by either company.
* Optional backends are in `Suggests` and used only conditionally. The vignette
  uses `knitr`'s native HTML format, without requiring `rmarkdown` or Pandoc.