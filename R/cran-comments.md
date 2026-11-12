## Test environments

* Local: Windows 10, R 4.6.1. `R CMD check --as-cran --no-manual`: 0 errors,
  0 warnings, 1 note. The manual was excluded because LaTeX is unavailable
  locally.
* GitHub Actions: ubuntu (R devel, release, oldrel-1, 4.1), macOS (release) and
  Windows (release): all pass.
* R-hub: Linux, Windows, macOS, `clang-asan` and `nosuggests` (R-devel):
  `Status: OK`.
* macOS builder, R-release (arm64): Status: OK, 0 errors, 0 warnings, 0 notes.
* win-builder, R-release (4.6.2) and R-oldrelease (4.5.3): 1 note.
* win-builder, R-devel: see the note below.

## R CMD check results

0 errors | 0 warnings | 1 note

* This is a resubmission of 0.1.1 (which was pending manual inspection). It
  adds the client-side `chart` output type (spec §8.5) and supersedes 0.1.1.
* "Possibly misspelled words in DESCRIPTION: PBC". This is the correct legal
  suffix in 'Posit Software, PBC', used in the trademark statement.

## win-builder R-devel

Recent win-builder R-devel runs reported
`Files named as vignettes but with no recognized vignette engine:
'inst/doc/getting-started.Rmd'`. The package contains no `.Rmd` file: the
vignette is `vignettes/getting-started.Rhtml`, built with `knitr::knitr`, and
the built tarball ships only the `.Rhtml`, `.R` and `.html` files. The same
tarball passes on win-builder R-release and R-oldrelease, on R-hub Windows,
Linux, macOS and `nosuggests` with R-devel, and on the macOS builder. An earlier
win-builder R-devel run on the previous `.Rmd` version of the vignette passed.
We believe the message comes from stale state on the win-builder R-devel
machine, and we would appreciate it if the CRAN team could confirm on their own
R-devel.

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