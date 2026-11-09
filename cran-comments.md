## Test environments

* local: Windows 10, R 4.6.1
* win-builder: R-devel, R-release
* macOS builder: R-release
* R-hub: (to be filled)

## R CMD check results

0 errors | 0 warnings | 1 note

* New submission.

## Downstream dependencies

There are currently no downstream dependencies for this package.

## Notes

* This package pairs an unmodified 'SAS' program with a 'Shiny' app. It does not
  require 'SAS', 'Python' or internet access to install or run its checks: the
  mock engine is used everywhere, and live-'SAS' tests are opt-in
  (`SASHINY_LIVE=1`) and skipped otherwise.
* 'SAS' is a registered trademark of SAS Institute Inc. and 'Shiny' is a
  registered trademark of Posit Software, PBC; this package is not affiliated
  with or endorsed by either company.
* Optional backends ('reticulate', 'mirai', 'bslib', 'DT', 'haven', 'readxl')
  are in `Suggests` and guarded with `rlang::check_installed()`.