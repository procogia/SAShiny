# Replay engine, registered engines and the recording writer (spec section 6.6).
#
# Besides saspy engines and pools, the public entry points accept two more
# kinds of engine:
#
# * the replay engine (`sas_replay()`), which serves recordings (spec section
#   8.3) only when each one carries provenance from a licensed 'SAS' run and was
#   made from the program on disk, and labels every replayed result as a
#   replay;
# * engine classes registered with `sas_register_engine()`, whose author
#   acknowledges that the engine runs every program on a live, licensed 'SAS'
#   system.
#
# `sas_record()` writes a recording from a live or registered engine's result,
# and `sas_engine_result()` builds a result for a registered engine.

# ---------------------------------------------------------------- replay engine

#' Replay recordings of runs made on a live, licensed 'SAS' system
#'
#' Creates an engine that serves recordings (spec section 8.3) instead of
#' submitting programs to 'SAS', for offline demos and static sites. A
#' recording is replayed only when it carries provenance from a licensed 'SAS'
#' run: the 'SAS' version (`&SYSVLONG`), the time it was recorded, and the
#' SHA-256 of the contract and program it was made from, which must match the
#' files on disk. Otherwise the run returns an error result whose
#' `metadata$engine_error` gives the reason, and nothing is replayed.
#'
#' A replayed result has `metadata$recording = "replayed"`,
#' `metadata$engine = "replay"` and a `metadata$notice` such as
#' `"Replayed from 9.04.01M0P061913, recorded 2015-07-30T12:00:00Z."`, which
#' the module's status text shows. Inputs that were never recorded give an
#' error result with `metadata$recording = "missing"`. Write recordings with
#' [sas_record()].
#'
#' The replay engine runs no `choices_from` query and needs no licence
#' acknowledgement, because it submits nothing to 'SAS'.
#'
#' @param recordings_dir Directory holding the recording files
#'   (`<key>.json`).
#' @return A `sashiny_engine_replay` object, accepted by [sas_run()],
#'   [sas_program_server()], [sas_app()] and [sas_pool()].
#' @seealso [sas_record()] to write recordings, spec section 6.6 (a).
#' @examples
#' contract <- sas_contract(system.file("examples", "minimal", "minimal.sashiny.yml",
#'   package = "SAShiny"
#' ))
#' # A recording of a run on licensed SAS; in an app, the result comes from
#' # sas_connect() or a registered engine and is written with sas_record().
#' live <- sas_engine_result(contract, "success",
#'   log = "NOTE: SASHINY-BEGIN-PROGRAM\nNOTE: SASHINY-END-PROGRAM\n",
#'   macros = list(N_ROWS = "5"), sas_version = "9.04.01M0P061913", engine = "sas94-batch"
#' )
#' recordings <- tempfile("recordings")
#' sas_record(recordings, contract, live)
#' engine <- sas_replay(recordings)
#' result <- sas_run(contract, engine, list(n_rows = 5))
#' result$metadata$notice
#' # Inputs that were never recorded are not replayed:
#' sas_run(contract, engine, list(n_rows = 6))$metadata$engine_error
#' @export
sas_replay <- function(recordings_dir) {
  if (!is.character(recordings_dir) || length(recordings_dir) != 1L || is.na(recordings_dir) ||
    !nzchar(recordings_dir)) {
    .sashiny_abort("engine", "recordings_dir must be a single directory path")
  }
  structure(
    list(recordings_dir = recordings_dir),
    class = c("sashiny_engine_replay", "sashiny_engine")
  )
}

#' @export
print.sashiny_engine_replay <- function(x, ...) {
  cat("<sashiny replay engine>\n  recordings: ", x$recordings_dir, "\n", sep = "")
  invisible(x)
}

#' Validate values and dataset files for an offline run.
#'
#' Shared by the replay engine and the internal mock: renders and validates the
#' values (spec section 4), resolves and converts the dataset files (section 7)
#' exactly like a live engine, and returns either the error result or what the
#' recording lookup needs.
#' @return A list with `result` (an error result, or `NULL`), `base` (metadata
#'   fields), `macros` and `files`.
#' @noRd
.sashiny_offline_prepare <- function(engine, contract, values, today, uploads, run_id,
                                     engine_name) {
  flags <- lapply(uploads %||% list(), function(v) !is.null(v) && !isFALSE(v))
  override <- .sashiny_choice_override(contract$cached_choices %||% sas_engine_choices(engine, contract))
  res <- sas_render_values(contract$data, values, today,
    choices_override = override, uploads = flags
  )
  base <- list(
    contract_sha256 = .sashiny_contract_sha256(contract),
    program_sha256 = .sashiny_program_sha256(contract),
    macros = res$macros,
    engine = engine_name,
    engine_version = as.character(utils::packageVersion("SAShiny"))
  )
  out <- list(result = NULL, base = base, macros = res$macros, files = list())
  if (length(res$issues) > 0L) {
    out$result <- .sashiny_invalid_result(run_id, base, .sashiny_issue_list(res$issues))
    return(out)
  }
  # Resolve and run the full section 7 conversion for every supplied dataset
  # input, exactly like the live engine, so a missing declared column, an
  # unparseable cell or an unreadable file is reported as V014 (section 6.1
  # step 2).
  files <- tryCatch(
    {
      found <- .sashiny_resolve_files(contract, uploads)
      for (iid in names(found)) {
        .sashiny_read_upload(found[[iid]], contract$data$inputs[[iid]])
      }
      found
    },
    sashiny_upload_error = function(e) e
  )
  if (inherits(files, "sashiny_upload_error")) {
    out$result <- .sashiny_invalid_result(run_id, base, list(list(
      code = "V014", message = conditionMessage(files)
    )))
    return(out)
  }
  out$files <- files
  out
}

#' Why the replay engine refuses a recording, or `""` (spec section 6.6 (a)).
#' @param recording The parsed recording (a named list).
#' @param contract_sha256,program_sha256 SHA-256 of the files on disk.
#' @noRd
.sashiny_replay_problem <- function(recording, contract_sha256, program_sha256) {
  filled <- function(name) {
    value <- recording[[name]]
    is.character(value) && length(value) == 1L && !is.na(value) && nzchar(value)
  }
  version <- recording$sashiny_recording
  if (!is.numeric(version) || length(version) != 1L || !identical(as.numeric(version), 1)) {
    return("it is not a version 1 SAShiny recording")
  }
  if (!filled("sas_version")) {
    return("it has no SAS version")
  }
  if (!filled("recorded_at")) {
    return("it has no recording time")
  }
  if (!filled("contract_sha256") || !identical(recording$contract_sha256, contract_sha256)) {
    return("it was made from a different contract")
  }
  if (!filled("program_sha256") || !identical(recording$program_sha256, program_sha256)) {
    return("it was made from a different version of the program")
  }
  ""
}

#' @exportS3Method sas_engine_run sashiny_engine_replay
sas_engine_run.sashiny_engine_replay <- function(engine, contract, values, today = Sys.Date(),
                                                 uploads = NULL, run_id = NULL) {
  run_id <- run_id %||% .sashiny_run_id()
  prep <- .sashiny_offline_prepare(engine, contract, values, today, uploads, run_id, "replay")
  if (!is.null(prep$result)) {
    return(prep$result)
  }
  base <- prep$base
  fail <- function(recording, message) {
    meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = "error"), base))
    meta$recording <- recording
    meta$engine_error <- message
    .sashiny_result(run_id, "error", metadata = meta)
  }
  key <- .sashiny_recording_key(contract, prep$macros, prep$files)
  path <- file.path(engine$recordings_dir, paste0(key, ".json"))
  if (!file.exists(path)) {
    return(fail("missing", "no recording of this run: these inputs were not recorded on SAS"))
  }
  recording <- tryCatch(jsonlite::fromJSON(path, simplifyVector = FALSE),
    error = function(e) NULL
  )
  problem <- if (is.list(recording) && !is.null(names(recording))) {
    .sashiny_replay_problem(recording, base$contract_sha256, base$program_sha256)
  } else {
    "it is not valid JSON"
  }
  if (nzchar(problem)) {
    return(fail("refused", paste("recording not replayed:", problem)))
  }
  status <- recording$status %||% "success"
  base$sas_version <- recording$sas_version
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = status), base))
  meta$recording <- "replayed"
  meta$recorded_at <- recording$recorded_at
  meta$notice <- sprintf("Replayed from %s, recorded %s.", recording$sas_version, recording$recorded_at)
  .sashiny_result(run_id, status,
    outputs = recording$outputs %||% list(),
    log = recording$log %||% "",
    metadata = meta
  )
}

# ---------------------------------------------------------------- registry

#' Registered engine classes (spec section 6.6 (b)): class name -> description.
#' @noRd
.sashiny_registry <- new.env(parent = emptyenv())
.sashiny_registry$engines <- character(0)

#' Register an engine class that runs on live, licensed 'SAS'
#'
#' Lets [sas_program_server()], [sas_app()], [sas_run()] and [sas_pool()]
#' accept engines of an S3 class you implement, for example an engine that
#' runs 'SAS' 9.4 in batch on the same machine. The class needs a
#' [sas_engine_run()] method that returns a result built with
#' [sas_engine_result()].
#'
#' @section Licence responsibility:
#' A registered engine MUST execute every run on a live 'SAS' system that you
#' are licensed to use, and the log and outputs it returns MUST be the ones that
#' 'SAS' run produced (spec section 6.6 (b)). 'SAShiny' cannot verify this:
#' registering with `license_ack = TRUE` is your acknowledgement. The
#' `SAShiny.license_ack` option and the `SASHINY_LICENSE_ACK` environment
#' variable do not register an engine.
#'
#' @param class The S3 class name of the engine (a single string). It must have
#'   a `sas_engine_run()` method and must not be one of 'SAShiny''s own classes
#'   (names starting with `sashiny_`).
#' @param license_ack Must be `TRUE`: you acknowledge that the engine runs on a
#'   live 'SAS' system you are licensed to use.
#' @param description A non-empty description of the 'SAS' system the engine
#'   runs on, for example `"SAS 9.4M0 batch on this machine"`.
#' @return `sas_register_engine()` and `sas_unregister_engine()` return `class`
#'   invisibly. `sas_registered_engines()` returns a named character vector of
#'   descriptions, named by class.
#' @seealso [sas_engine_result()], [sas_record()].
#' @examples
#' # A toy engine class. A real one submits the program to licensed SAS.
#' sas_engine_run.my_batch_engine <- function(engine, contract, values, today = Sys.Date(),
#'                                            uploads = NULL, run_id = NULL) {
#'   stop("runs SAS in batch; not run in this example")
#' }
#' registerS3method("sas_engine_run", "my_batch_engine", sas_engine_run.my_batch_engine)
#' sas_register_engine("my_batch_engine",
#'   license_ack = TRUE,
#'   description = "SAS 9.4 batch on this machine"
#' )
#' sas_registered_engines()
#' sas_unregister_engine("my_batch_engine")
#' @export
sas_register_engine <- function(class, license_ack = FALSE, description = NULL) {
  if (!is.character(class) || length(class) != 1L || is.na(class) || !nzchar(class)) {
    .sashiny_abort("engine", "class must be a single S3 class name")
  }
  if (startsWith(class, "sashiny_")) {
    .sashiny_abort("engine", "class ", class, " is one of SAShiny's own engine classes and ",
      "cannot be registered")
  }
  if (!identical(license_ack, TRUE)) {
    .sashiny_abort("license",
      "SAS licence not acknowledged: register an engine only if it runs every program on a ",
      "live 'SAS' system you are licensed to use, and confirm this with license_ack = TRUE")
  }
  if (!is.character(description) || length(description) != 1L || is.na(description) ||
    !nzchar(trimws(description))) {
    .sashiny_abort("engine", "description must name the SAS system the engine runs on")
  }
  method <- utils::getS3method("sas_engine_run", class, optional = TRUE, envir = parent.frame())
  if (is.null(method)) {
    .sashiny_abort("engine", "class ", class, " has no sas_engine_run() method")
  }
  engines <- .sashiny_registry$engines
  engines[[class]] <- trimws(description)
  .sashiny_registry$engines <- engines
  invisible(class)
}

#' @rdname sas_register_engine
#' @export
sas_unregister_engine <- function(class) {
  engines <- .sashiny_registry$engines
  .sashiny_registry$engines <- engines[names(engines) != class]
  invisible(class)
}

#' @rdname sas_register_engine
#' @export
sas_registered_engines <- function() {
  .sashiny_registry$engines
}

# ---------------------------------------------------------------- results and recordings

#' Build a run result for a registered engine
#'
#' Builds a `sashiny_result` with the run metadata of spec section 8.4: the
#' SHA-256 of the contract and program on disk, timestamps, the engine name and
#' version, and the 'SAS' version. A registered engine (see
#' [sas_register_engine()]) returns it from its [sas_engine_run()] method.
#'
#' @param contract A `sashiny_contract` object.
#' @param status `"success"`, `"warning"` or `"error"` (spec section 6.5),
#'   derived from the 'SAS' log.
#' @param outputs A named list of output values (spec section 8.1), keyed by
#'   output id.
#' @param log The full main-submission log text from 'SAS'.
#' @param macros The rendered macro values (`sas_render_values()$macros`).
#' @param sas_version The 'SAS' version (`&SYSVLONG`) of the run.
#' @param engine The engine name, for example `"sas94-batch"`.
#' @param run_id The run identifier (defaults to a generated UUID).
#' @param started_at,ended_at Start and end times, as `POSIXct` or UTC ISO
#'   8601 strings (default: now).
#' @return A `sashiny_result` object.
#' @examples
#' contract <- sas_contract(system.file("examples", "minimal", "minimal.sashiny.yml",
#'   package = "SAShiny"
#' ))
#' result <- sas_engine_result(contract, "success",
#'   log = "NOTE: SASHINY-BEGIN-PROGRAM\nNOTE: SASHINY-END-PROGRAM\n",
#'   macros = list(N_ROWS = "5"), sas_version = "9.04.01M0P061913", engine = "sas94-batch"
#' )
#' result$metadata$program_sha256
#' @export
sas_engine_result <- function(contract, status, outputs = list(), log = "", macros = list(),
                              sas_version = "", engine = "", run_id = NULL,
                              started_at = NULL, ended_at = NULL) {
  if (!inherits(contract, "sashiny_contract")) {
    .sashiny_abort("engine", "contract must be a sashiny_contract")
  }
  valid_status <- is.character(status) && length(status) == 1L &&
    status %in% c("success", "warning", "error")
  if (!valid_status) {
    .sashiny_abort("engine", "status must be \"success\", \"warning\" or \"error\"")
  }
  stamp <- function(x) {
    if (inherits(x, "POSIXt")) format(x, "%Y-%m-%dT%H:%M:%SZ", tz = "UTC") else x
  }
  run_id <- run_id %||% .sashiny_run_id()
  meta <- .sashiny_metadata(run_id, status,
    contract_sha256 = .sashiny_contract_sha256(contract),
    program_sha256 = .sashiny_program_sha256(contract),
    macros = as.list(macros), engine = engine,
    engine_version = as.character(utils::packageVersion("SAShiny")),
    sas_version = sas_version %||% "", started_at = stamp(started_at), ended_at = stamp(ended_at)
  )
  .sashiny_result(run_id, status, outputs = outputs %||% list(), log = log %||% "", metadata = meta)
}

#' Write a run result as a recording
#'
#' Writes `result` as a recording file (spec section 8.3) that [sas_replay()]
#' can replay, and returns its path. The file name is the recording key of the
#' rendered macros (`result$metadata$macros`) and the dataset files, so
#' recordings made in R and Python are interchangeable. Empty `macros` and
#' `outputs` are written as JSON objects.
#'
#' Only results of a live run can be recorded: the result must carry its 'SAS'
#' version, must not be a replay or a cache hit, and its contract and program
#' SHA-256 must match the files on disk.
#'
#' @param directory Directory to write the recording into (created if needed).
#' @param contract The `sashiny_contract` the result was run from.
#' @param result A `sashiny_result` from a live or registered engine.
#' @param uploads The `uploads` the run was given (dataset input files), as for
#'   [sas_engine_run()].
#' @return The path of the recording file, invisibly.
#' @examples
#' contract <- sas_contract(system.file("examples", "minimal", "minimal.sashiny.yml",
#'   package = "SAShiny"
#' ))
#' # In an app, `result` comes from a live or registered engine.
#' result <- sas_engine_result(contract, "success",
#'   macros = list(N_ROWS = "5"), sas_version = "9.04.01M0P061913", engine = "sas94-batch"
#' )
#' path <- sas_record(tempfile(), contract, result)
#' basename(path)
#' @export
sas_record <- function(directory, contract, result, uploads = NULL) {
  if (!inherits(contract, "sashiny_contract")) {
    contract <- sas_contract(contract)
  }
  meta <- result$metadata %||% list()
  refuse <- function(...) .sashiny_abort("engine", "cannot record this result: ", ...)
  if (!nzchar(meta$sas_version %||% "")) {
    refuse("it has no SAS version, so it did not come from a live SAS run")
  }
  if (!is.null(meta$recording)) {
    refuse("it is itself a replay (metadata$recording is \"", meta$recording, "\")")
  }
  if (isTRUE(meta$cache_hit)) {
    refuse("it is a result-cache hit")
  }
  contract_sha <- .sashiny_contract_sha256(contract)
  if (!nzchar(contract_sha)) {
    refuse("the contract has no file on disk")
  }
  if (!identical(meta$contract_sha256 %||% "", contract_sha)) {
    refuse("it was made from a different contract")
  }
  program_sha <- .sashiny_program_sha256(contract)
  if (!identical(meta$program_sha256 %||% "", program_sha)) {
    refuse("it was made from a different version of the program")
  }
  macros <- as.list(meta$macros %||% list())
  files <- .sashiny_resolve_files(contract, uploads)
  object <- function(x) if (length(x) == 0L) structure(list(), names = character(0)) else x
  payload <- list(
    sashiny_recording = 1L,
    status = result$status,
    log = result$log %||% "",
    outputs = object(result$outputs %||% list()),
    sas_version = meta$sas_version,
    contract_sha256 = contract_sha,
    program_sha256 = program_sha,
    macros = object(macros),
    recorded_at = .sashiny_now()
  )
  dir.create(directory, recursive = TRUE, showWarnings = FALSE)
  key <- .sashiny_recording_key(contract, macros, files)
  path <- file.path(directory, paste0(key, ".json"))
  json <- jsonlite::toJSON(payload,
    auto_unbox = TRUE, null = "null", na = "null", digits = I(17), pretty = TRUE
  )
  writeLines(enc2utf8(as.character(json)), path, useBytes = TRUE)
  invisible(path)
}
