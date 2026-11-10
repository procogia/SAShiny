# Mock engine with record/replay for SAShiny.
#
# Implements the engine interface without SAS. In replay mode it returns recorded
# results keyed by the contract hash and rendered macros; in recording mode it
# captures live runs for later replay. This powers CRAN/PyPI checks, examples,
# vignettes and the demo's offline fallback (issue #5).

#' SHA-256 of raw bytes, hex-encoded.
#' @noRd
.sashiny_sha256 <- function(bytes) {
  as.character(openssl::sha256(bytes))
}

#' Generate a run id (UUID-like, spec section 6.1).
#' @noRd
.sashiny_run_id <- function() {
  paste0(
    paste(sample(c(0:9, letters[1:6]), 8, replace = TRUE), collapse = ""),
    "-",
    paste(sample(c(0:9, letters[1:6]), 4, replace = TRUE), collapse = ""),
    "-",
    paste(sample(c(0:9, letters[1:6]), 4, replace = TRUE), collapse = ""),
    "-",
    paste(sample(c(0:9, letters[1:6]), 4, replace = TRUE), collapse = ""),
    "-",
    paste(sample(c(0:9, letters[1:6]), 12, replace = TRUE), collapse = "")
  )
}

#' SHA-256 of the contract YAML bytes as stored on disk (spec section 8).
#'
#' Returns `""` for contracts built in memory without a source file.
#' @noRd
.sashiny_contract_sha256 <- function(contract) {
  path <- contract$path
  if (is.null(path) || !file.exists(path)) {
    return("")
  }
  .sashiny_sha256(readBin(path, "raw", n = file.info(path)$size))
}

#' Deterministic recording key: contract hash + rendered macros.
#' @noRd
.sashiny_recording_key <- function(contract, macros) {
  contract_json <- jsonlite::toJSON(contract$data, auto_unbox = TRUE, null = "null")
  macro_json <- jsonlite::toJSON(macros, auto_unbox = TRUE, null = "null")
  .sashiny_sha256(charToRaw(paste0(contract_json, "\n", macro_json)))
}

#' Create a mock engine
#'
#' A mock engine that replays recorded results (issue #5). When `recordings_dir`
#' is `NULL`, it returns an empty successful result for any run.
#'
#' @param recordings_dir Directory holding recording files (`<key>.json`).
#' @param record When `TRUE`, write recordings instead of replaying.
#' @return A `sashiny_engine_mock` object (a named list).
#' @examples
#' engine <- sas_engine_mock()
#' engine
#' @export
sas_engine_mock <- function(recordings_dir = NULL, record = FALSE) {
  structure(
    list(recordings_dir = recordings_dir, record = record),
    class = "sashiny_engine_mock"
  )
}

#' Run a contract with the mock engine
#'
#' @param engine A `sashiny_engine_mock` object.
#' @param contract A `sashiny_contract` object.
#' @param values A named list of input values.
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to `TRUE`.
#' @param run_id The run identifier (defaults to a generated UUID).
#' @return A `sashiny_result` object.
#' @export
sas_engine_run <- function(engine, contract, values, today = Sys.Date(),
                           uploads = NULL, run_id = NULL) {
  run_id <- run_id %||% .sashiny_run_id()
  data <- contract$data
  res <- sas_render_values(data, values, today, uploads = uploads)
  macros <- res$macros
  if (length(res$issues) > 0L) {
    return(sashiny_result(
      run_id, "error",
      metadata = .sashiny_metadata(
        run_id, "error",
        contract_sha256 = .sashiny_contract_sha256(contract),
        program_sha256 = .sashiny_sha256(readBin(
          file.path(contract$base_dir, data$program), "raw",
          n = file.info(file.path(contract$base_dir, data$program))$size
        )),
        macros = macros,
        engine = "mock",
        engine_version = "0.0.1"
      )
    ))
  }

  key <- .sashiny_recording_key(contract, macros)
  recording <- .sashiny_load_recording(engine$recordings_dir, key)
  if (!is.null(recording)) {
    return(.sashiny_replay(recording, run_id, macros, contract))
  }

  sashiny_result(
    run_id, "success",
    metadata = .sashiny_metadata(
      run_id, "success",
      contract_sha256 = .sashiny_contract_sha256(contract),
      program_sha256 = .sashiny_sha256(readBin(
        file.path(contract$base_dir, data$program), "raw",
        n = file.info(file.path(contract$base_dir, data$program))$size
      )),
      macros = macros,
      engine = "mock",
      engine_version = "0.0.1"
    )
  )
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

#' Replay a recording into a result object.
#' @noRd
.sashiny_replay <- function(recording, run_id, macros, contract) {
  sashiny_result(
    run_id,
    recording$status %||% "success",
    outputs = recording$outputs %||% list(),
    log = recording$log %||% "",
    metadata = .sashiny_metadata(
      run_id,
      recording$status %||% "success",
      contract_sha256 = recording$contract_sha256 %||% "",
      program_sha256 = recording$program_sha256 %||% "",
      macros = macros,
      engine = "mock",
      engine_version = "0.0.1",
      sas_version = recording$sas_version %||% ""
    )
  )
}

#' Save a recording for later replay (recording mode).
#'
#' @param engine A `sashiny_engine_mock` object.
#' @param contract A `sashiny_contract` object.
#' @param macros A named list of rendered macro values.
#' @param recording A named list to record.
#' @return Invisibly, the path written.
#' @export
sas_engine_record <- function(engine, contract, macros, recording) {
  if (is.null(engine$recordings_dir)) {
    stop("recordings_dir is not set")
  }
  dir.create(engine$recordings_dir, recursive = TRUE, showWarnings = FALSE)
  key <- .sashiny_recording_key(contract, macros)
  path <- file.path(engine$recordings_dir, paste0(key, ".json"))
  writeLines(jsonlite::toJSON(recording, auto_unbox = TRUE, null = "null", pretty = TRUE),
    path,
    useBytes = TRUE
  )
  invisible(path)
}
