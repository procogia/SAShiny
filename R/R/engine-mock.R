# Internal offline mock engine: a TEST FIXTURE, not part of the public API.
#
# CRAN: 'R CMD check' has no 'SAS', so the test suite needs a way to exercise
# the Shiny module, the pool and result handling without one. This engine
# replays hand-written recordings (spec section 8.3) for that purpose only. It
# is not exported and it refuses to run outside a testthat run, and the public
# entry points accept only live engines outside tests (`.sashiny_check_engine()`).
# Unlike the public replay engine (`sas_replay()`, engine-replay.R), it does not
# check provenance, so users cannot feed it logs or results that did not come
# from a live, licensed 'SAS' system (spec section 6.6).

#' Whether the code is running inside a testthat test run.
#'
#' testthat sets `TESTTHAT=true` for the test process; 'callr' children
#' inherit it.
#' @noRd
.sashiny_testing <- function() {
  identical(Sys.getenv("TESTTHAT"), "true")
}

#' Stop unless running inside the test suite.
#' @noRd
.sashiny_require_testing <- function() {
  if (!.sashiny_testing()) {
    .sashiny_abort("engine", "the mock engine is an internal test fixture; connect to SAS with sas_connect()")
  }
  invisible(TRUE)
}

#' Create the internal mock engine (tests only)
#'
#' Replays recordings (spec section 8.3). When no recording matches, it
#' returns an empty successful result with `metadata$recording` set to
#' `"missing"`.
#'
#' @param recordings_dir Directory holding recording files (`<key>.json`).
#' @param choices Choices for `choices_from` inputs, a named list keyed by input
#'   id of character vectors or `list(value, label)` items, standing in for the
#'   SAS query of spec section 6.4.
#' @return A `sashiny_engine_mock` object.
#' @noRd
.sashiny_engine_mock <- function(recordings_dir = NULL, choices = NULL) {
  .sashiny_require_testing()
  normalised <- lapply(choices %||% list(), function(items) {
    lapply(items, function(c) {
      if (is.list(c)) {
        list(value = c$value, label = c$label %||% c$value)
      } else {
        list(value = c, label = c)
      }
    })
  })
  structure(
    list(recordings_dir = recordings_dir, choices = normalised),
    class = c("sashiny_engine_mock", "sashiny_engine")
  )
}

#' Recording key for a run (spec section 8.3)
#'
#' @param contract A `sashiny_contract` object.
#' @param macros A named list of rendered macro values.
#' @param files A named list of upload files (from `.sashiny_resolve_files()`)
#'   or of file paths.
#' @noRd
.sashiny_recording_key <- function(contract, macros, files = list()) {
  inputs <- contract$data$inputs %||% list()
  uploads <- character(0)
  for (iid in names(inputs)) {
    if (identical(inputs[[iid]]$type, "dataset") && !is.null(files[[iid]])) {
      path <- files[[iid]]
      if (inherits(path, "sashiny_upload_file")) path <- path$path
      uploads[[iid]] <- .sashiny_sha256(.sashiny_read_bytes(path))
    }
  }
  .sashiny_recording_key_hash(.sashiny_contract_sha256(contract), macros, uploads)
}

#' Load a recording file, or NULL when absent.
#' @noRd
.sashiny_load_recording <- function(recordings_dir, key) {
  if (is.null(recordings_dir)) {
    return(NULL)
  }
  path <- file.path(recordings_dir, paste0(key, ".json"))
  if (!file.exists(path)) {
    return(NULL)
  }
  jsonlite::fromJSON(path, simplifyVector = FALSE)
}

#' @exportS3Method sas_engine_choices sashiny_engine_mock
sas_engine_choices.sashiny_engine_mock <- function(engine, contract) {
  inputs <- contract$data$inputs %||% list()
  keep <- vapply(names(engine$choices), function(iid) {
    !is.null(inputs[[iid]]$choices_from)
  }, logical(1))
  engine$choices[keep]
}

#' @exportS3Method sas_engine_run sashiny_engine_mock
sas_engine_run.sashiny_engine_mock <- function(engine, contract, values, today = Sys.Date(),
                                               uploads = NULL, run_id = NULL) {
  .sashiny_require_testing()
  run_id <- run_id %||% .sashiny_run_id()
  prep <- .sashiny_offline_prepare(engine, contract, values, today, uploads, run_id, "mock")
  if (!is.null(prep$result)) {
    return(prep$result)
  }
  base <- prep$base
  key <- .sashiny_recording_key(contract, prep$macros, prep$files)
  recording <- .sashiny_load_recording(engine$recordings_dir, key)
  if (is.null(recording)) {
    meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = "success"), base))
    meta$recording <- "missing"
    return(.sashiny_result(run_id, "success", metadata = meta))
  }
  status <- recording$status %||% "success"
  base$sas_version <- recording$sas_version %||% ""
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = status), base))
  meta$recording <- "replayed"
  meta$recorded_at <- recording$recorded_at %||% ""
  .sashiny_result(run_id, status,
    outputs = recording$outputs %||% list(),
    log = recording$log %||% "",
    metadata = meta
  )
}

#' Write a recording for the mock engine (tests only).
#'
#' @param engine A `sashiny_engine_mock` object.
#' @param contract A `sashiny_contract` object.
#' @param macros A named list of rendered macro values.
#' @param recording A named list to record.
#' @param files A named list of upload files or paths for dataset inputs.
#' @return Invisibly, the path written.
#' @noRd
.sashiny_write_recording <- function(engine, contract, macros, recording, files = list()) {
  .sashiny_require_testing()
  if (is.null(engine$recordings_dir)) {
    .sashiny_abort("engine", "recordings_dir is not set")
  }
  dir.create(engine$recordings_dir, recursive = TRUE, showWarnings = FALSE)
  key <- .sashiny_recording_key(contract, macros, files)
  path <- file.path(engine$recordings_dir, paste0(key, ".json"))
  payload <- c(list(sashiny_recording = 1L), recording)
  json <- jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = I(17), pretty = TRUE)
  writeLines(enc2utf8(as.character(json)), path, useBytes = TRUE)
  invisible(path)
}
