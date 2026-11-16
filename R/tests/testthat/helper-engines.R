# Engine helpers for the test suite.
#
# R CMD check has no SAS. The tests therefore use two internal fixtures:
# the offline mock engine (`.sashiny_engine_mock()`, which replays recordings)
# and a saspy engine backed by a fake session (`helper-fakesas.R`). Neither is
# reachable through the public API (spec section 6.6).

# A saspy engine for tests: licence acknowledged, configuration not validated.
test_saspy_engine <- function(cfg = list(java = "java"), session_factory = NULL,
                              license_ack = TRUE) {
  .sashiny_new_saspy_engine(cfg,
    session_factory = session_factory, license_ack = license_ack, backend = "test"
  )
}

# Save a run result as a recording (spec section 8.3) so the mock can replay it.
test_save_recording <- function(directory, contract, result, files = list()) {
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  key <- .sashiny_recording_key(contract, result$metadata$macros, files)
  empty <- function(x) if (length(x) == 0L) structure(list(), names = character(0)) else x
  payload <- list(
    sashiny_recording = 1L, status = result$status, log = result$log,
    outputs = empty(result$outputs), sas_version = result$metadata$sas_version %||% "",
    macros = empty(result$metadata$macros), recorded_at = "2026-11-11T00:00:00Z"
  )
  path <- file.path(directory, paste0(key, ".json"))
  json <- jsonlite::toJSON(payload,
    auto_unbox = TRUE, null = "null", na = "null", digits = I(17), pretty = TRUE
  )
  writeLines(enc2utf8(as.character(json)), path, useBytes = TRUE)
  path
}

# Run `code` as if outside the test suite (TESTTHAT unset), restoring it after.
outside_tests <- function(code) {
  old <- Sys.getenv("TESTTHAT", unset = NA)
  Sys.unsetenv("TESTTHAT")
  on.exit(if (is.na(old)) Sys.unsetenv("TESTTHAT") else Sys.setenv(TESTTHAT = old), add = TRUE)
  force(code)
}
