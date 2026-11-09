# Shared test helpers for the SAShiny conformance tests.

#' Locate the spec/fixtures directory.
#'
#' In development, tests run from R/tests/testthat; the repo root is ../../..
#' At build time, spec files are copied to inst/spec.
#' @noRd
.sashiny_fixtures <- function() {
  dev <- normalizePath(file.path("..", "..", "..", "spec", "fixtures"),
                       mustWork = FALSE)
  if (dir.exists(dev)) {
    return(dev)
  }
  system.file("spec", "fixtures", package = "SAShiny")
}

# The fixed "today" used by the fixtures (spec/fixtures/README.md).
.sashiny_today <- as.Date("2026-11-11")