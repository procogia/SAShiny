# Engine generics, recordings and the mock engine for SAShiny.
#
# Every engine (mock, saspy, pool) implements the S3 generics
# `sas_engine_run()`, `sas_engine_choices()` and `sas_engine_close()`. The mock
# engine runs without SAS: it replays recordings (spec section 8.3) keyed by the
# contract bytes, the rendered macros and the uploaded files. Recordings are
# written by a live engine (`sas_connect(..., record_to = )`) and are shared with
# the Python library. This powers CRAN/PyPI checks, examples, vignettes and the
# demo's offline fallback (issue #5).

#' SHA-256 of raw bytes, hex-encoded.
#' @noRd
.sashiny_sha256 <- function(bytes) {
  paste(as.character(unclass(openssl::sha256(bytes))), collapse = "")
}

#' Generate a random UUID run id (spec section 6.1).
#'
#' Uses openssl's random bytes so the caller's random number stream is left
#' untouched.
#' @noRd
.sashiny_run_id <- function() {
  bytes <- openssl::rand_bytes(16L)
  bytes[7] <- as.raw(bitwOr(bitwAnd(as.integer(bytes[7]), 0x0f), 0x40))
  bytes[9] <- as.raw(bitwOr(bitwAnd(as.integer(bytes[9]), 0x3f), 0x80))
  hex <- paste(as.character(bytes), collapse = "")
  starts <- c(1L, 9L, 13L, 17L, 21L)
  ends <- c(8L, 12L, 16L, 20L, 32L)
  paste(substring(hex, starts, ends), collapse = "-")
}

#' SHA-256 of the contract YAML bytes as stored on disk (spec section 8.4).
#'
#' Returns `""` for contracts built in memory without a source file.
#' @noRd
.sashiny_contract_sha256 <- function(contract) {
  path <- contract$path
  if (is.null(path) || !file.exists(path)) {
    return("")
  }
  .sashiny_sha256(.sashiny_read_bytes(path))
}

#' SHA-256 of the SAS program bytes as stored on disk (spec section 8.4).
#' @noRd
.sashiny_program_sha256 <- function(contract) {
  .sashiny_sha256(.sashiny_read_bytes(file.path(contract$base_dir, contract$data$program)))
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

#' A JSON object even when empty.
#' @noRd
.sashiny_json_object <- function(x) {
  if (length(x) == 0L) structure(list(), names = character(0)) else x
}

#' Write a result as a recording file (spec section 8.3).
#' @noRd
.sashiny_save_recording <- function(directory, key, result) {
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  meta <- result$metadata
  payload <- list(
    sashiny_recording = 1L,
    status = result$status,
    log = result$log,
    outputs = .sashiny_json_object(result$outputs),
    sas_version = meta$sas_version %||% "",
    contract_sha256 = meta$contract_sha256 %||% "",
    program_sha256 = meta$program_sha256 %||% "",
    macros = .sashiny_json_object(meta$macros),
    recorded_at = .sashiny_now()
  )
  path <- file.path(directory, paste0(key, ".json"))
  json <- jsonlite::toJSON(payload,
    auto_unbox = TRUE, null = "null", na = "null", digits = NA, pretty = TRUE
  )
  writeLines(enc2utf8(as.character(json)), path, useBytes = TRUE)
  path
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

# ---------------------------------------------------------------- generics

#' Run a contract on an engine
#'
#' Validates and renders the inputs, runs the SAS program and collects the
#' outputs. Methods exist for the mock engine ([sas_engine_mock()]), the saspy
#' engine ([sas_connect()], [sas_engine_saspy()]) and session pools
#' ([sas_pool()]).
#'
#' @param engine An engine object.
#' @param contract A `sashiny_contract` object.
#' @param values A named list of input values in the contract's JSON form.
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to the supplied file:
#'   a path, a Shiny `fileInput` value, or `TRUE` for the input's `sample`.
#' @param run_id The run identifier (defaults to a generated UUID).
#' @return A `sashiny_result` object. Its `outputs` hold the language-neutral
#'   values of spec section 8.1, keyed by output id.
#' @examples
#' dir <- tempfile("sashiny-")
#' dir.create(dir)
#' writeLines(c(
#'   "sashiny: 1",
#'   "program: program.sas",
#'   "outputs:",
#'   "  log:",
#'   "    type: log"
#' ), file.path(dir, "contract.sashiny.yml"))
#' writeLines("proc print data=sashelp.class; run;", file.path(dir, "program.sas"))
#' contract <- sas_contract(file.path(dir, "contract.sashiny.yml"))
#' result <- sas_engine_run(sas_engine_mock(), contract, list())
#' result$metadata$recording
#' @export
sas_engine_run <- function(engine, contract, values, today = Sys.Date(),
                           uploads = NULL, run_id = NULL) {
  UseMethod("sas_engine_run")
}

#' Read the choices of `choices_from` inputs
#'
#' Runs the query of spec section 6.4 for every input with `choices_from`.
#'
#' @param engine An engine object.
#' @param contract A `sashiny_contract` object.
#' @return A named list keyed by input id; each element is a list of
#'   `list(value, label)`. Engines without SAS return the choices they were
#'   given, or an empty list.
#' @export
sas_engine_choices <- function(engine, contract) {
  UseMethod("sas_engine_choices")
}

#' @export
sas_engine_choices.default <- function(engine, contract) {
  list()
}

#' Close an engine
#'
#' Ends any SAS session the engine holds. Safe to call more than once.
#'
#' @param engine An engine object.
#' @return Invisibly, `NULL`.
#' @export
sas_engine_close <- function(engine) {
  UseMethod("sas_engine_close")
}

#' @export
sas_engine_close.default <- function(engine) {
  invisible(NULL)
}

#' A failed result that never reached SAS (input or upload validation).
#' @noRd
.sashiny_invalid_result <- function(run_id, base, issues) {
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = "error"), base))
  meta$issues <- issues
  sashiny_result(run_id, "error", metadata = meta)
}

#' Issues as plain lists for result metadata.
#' @noRd
.sashiny_issue_list <- function(issues) {
  lapply(issues, function(i) list(code = i$code, input = i$path))
}

#' `choices_override` for `sas_render_values()` from engine choices.
#' @noRd
.sashiny_choice_override <- function(choices) {
  if (length(choices) == 0L) {
    return(NULL)
  }
  lapply(choices, function(items) vapply(items, function(c) c$value, character(1)))
}

# ---------------------------------------------------------------- mock

#' Create a mock engine
#'
#' A mock engine that replays recorded runs (spec section 8.3). When no
#' recording matches, it returns an empty successful result with
#' `metadata$recording` set to `"missing"`.
#'
#' @param recordings_dir Directory holding recording files (`<key>.json`).
#' @param record Kept for backward compatibility; record live runs with
#'   `sas_connect(..., record_to = )` instead.
#' @param choices Choices for `choices_from` inputs, a named list keyed by input
#'   id of character vectors or `list(value, label)` items, standing in for the
#'   SAS query of spec section 6.4.
#' @return A `sashiny_engine_mock` object.
#' @examples
#' engine <- sas_engine_mock()
#' engine
#' @export
sas_engine_mock <- function(recordings_dir = NULL, record = FALSE, choices = NULL) {
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
    list(recordings_dir = recordings_dir, record = record, choices = normalised),
    class = c("sashiny_engine_mock", "sashiny_engine")
  )
}

#' @export
print.sashiny_engine_mock <- function(x, ...) {
  cat("<sashiny mock engine>\n")
  cat("  recordings:", x$recordings_dir %||% "(none)", "\n")
  invisible(x)
}

#' @export
sas_engine_choices.sashiny_engine_mock <- function(engine, contract) {
  inputs <- contract$data$inputs %||% list()
  keep <- vapply(names(engine$choices), function(iid) {
    !is.null(inputs[[iid]]$choices_from)
  }, logical(1))
  engine$choices[keep]
}

#' @export
sas_engine_run.sashiny_engine_mock <- function(engine, contract, values, today = Sys.Date(),
                                               uploads = NULL, run_id = NULL) {
  run_id <- run_id %||% .sashiny_run_id()
  flags <- lapply(uploads %||% list(), function(v) !is.null(v) && !isFALSE(v))
  override <- .sashiny_choice_override(sas_engine_choices(engine, contract))
  res <- sas_render_values(contract$data, values, today,
    choices_override = override, uploads = flags
  )
  base <- list(
    contract_sha256 = .sashiny_contract_sha256(contract),
    program_sha256 = .sashiny_program_sha256(contract),
    macros = res$macros,
    engine = "mock",
    engine_version = as.character(utils::packageVersion("SAShiny"))
  )
  if (length(res$issues) > 0L) {
    return(.sashiny_invalid_result(run_id, base, .sashiny_issue_list(res$issues)))
  }
  files <- tryCatch(.sashiny_resolve_files(contract, uploads),
    sashiny_upload_error = function(e) e
  )
  if (inherits(files, "sashiny_upload_error")) {
    return(.sashiny_invalid_result(run_id, base, list(list(
      code = "V014", message = conditionMessage(files)
    ))))
  }

  key <- .sashiny_recording_key(contract, res$macros, files)
  recording <- .sashiny_load_recording(engine$recordings_dir, key)
  if (is.null(recording)) {
    meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = "success"), base))
    meta$recording <- "missing"
    return(sashiny_result(run_id, "success", metadata = meta))
  }
  status <- recording$status %||% "success"
  base$sas_version <- recording$sas_version %||% ""
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = status), base))
  meta$recording <- "replayed"
  meta$recorded_at <- recording$recorded_at %||% ""
  sashiny_result(run_id, status,
    outputs = recording$outputs %||% list(),
    log = recording$log %||% "",
    metadata = meta
  )
}

#' Save a recording for later replay
#'
#' Writes a raw recording list as `<key>.json` in the engine's
#' `recordings_dir`. Live engines record complete runs automatically with
#' `sas_connect(..., record_to = )`.
#'
#' @param engine A `sashiny_engine_mock` object.
#' @param contract A `sashiny_contract` object.
#' @param macros A named list of rendered macro values.
#' @param recording A named list to record.
#' @param files A named list of upload files or paths for dataset inputs.
#' @return Invisibly, the path written.
#' @export
sas_engine_record <- function(engine, contract, macros, recording, files = list()) {
  if (is.null(engine$recordings_dir)) {
    stop("recordings_dir is not set", call. = FALSE)
  }
  dir.create(engine$recordings_dir, recursive = TRUE, showWarnings = FALSE)
  key <- .sashiny_recording_key(contract, macros, files)
  path <- file.path(engine$recordings_dir, paste0(key, ".json"))
  payload <- c(list(sashiny_recording = 1L), recording)
  json <- jsonlite::toJSON(payload, auto_unbox = TRUE, null = "null", digits = NA, pretty = TRUE)
  writeLines(enc2utf8(as.character(json)), path, useBytes = TRUE)
  invisible(path)
}
