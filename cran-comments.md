## Test environments

* Local: Windows 10, R 4.6.1. Full `R CMD check --no-manual`: 0 errors,
  0 warnings, 0 notes. The manual was excluded because LaTeX is unavailable.
* R-hub: Linux, Windows, macOS and `clang-asan` (R-devel): `Status: OK`.
* R-hub `nosuggests`: `Status: OK` in run 42838546509. The vignette uses a
  `knitr` HTML vignette and the testthat suite runs conditionally.
* macOS builder, R-release (arm64): Status: OK, 0 errors, 0 warnings, 0 notes.
* win-builder, R-devel, R-release and R-oldrelease: submitted; results are emailed
  to the maintainer and must be reviewed before submission.

## R CMD check results

The full local check is clean. CRAN incoming checks report only "New submission".

## Downstream dependencies

There are currently no downstream dependencies for this package.

## Notes

* This package pairs an unmodified 'SAS' program with a 'Shiny' app. It does not
  require 'SAS', 'Python' or internet access to install or run its tests: the
  mock engine is used, and live-'SAS' tests are opt-in (`SASHINY_LIVE=1`).
* 'SAS' is a registered trademark of SAS Institute Inc. and 'Shiny' is a
  registered trademark of Posit Software, PBC; this package is not affiliated
  with or endorsed by either company.
* Optional backends are in `Suggests` and used only conditionally. The vignette
  uses `knitr`'s native HTML format, without requiring `rmarkdown` or Pandoc.