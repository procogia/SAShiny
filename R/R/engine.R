# Engine generics and shared engine helpers for SAShiny.
#
# Every engine (saspy, pool, replay, registered engines and the internal test
# mock) implements the S3 generics `sas_engine_run()`, `sas_engine_choices()`
# and `sas_engine_close()`. Public engines run on a live, licensed 'SAS'
# system, or replay recordings of such runs (spec section 6.6).

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

# ---------------------------------------------------------------- generics

#' Run a contract on an engine
#'
#' Validates and renders the inputs, runs the SAS program on a live 'SAS'
#' system and collects the outputs. Methods exist for the saspy engine
#' ([sas_connect()], [sas_engine_saspy()]) and session pools ([sas_pool()]).
#'
#' @param engine An engine from [sas_connect()], [sas_engine_saspy()] or
#'   [sas_pool()].
#' @param contract A `sashiny_contract` object.
#' @param values A named list of input values in the contract's JSON form.
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to the supplied file:
#'   a path, a Shiny `fileInput` value, or `TRUE` for the input's `sample`.
#' @param run_id The run identifier (defaults to a generated UUID).
#' @return A `sashiny_result` object (a named list with `run_id`, `status`,
#'   `outputs`, `log` and `metadata`). Its `outputs` hold the language-neutral
#'   values of spec section 8.1, keyed by output id. Failures (invalid inputs,
#'   no licence acknowledgement, connection errors) are returned as a result
#'   with status `"error"`; they are not raised.
#' @examples
#' contract <- sas_contract(system.file("examples", "minimal", "minimal.sashiny.yml",
#'   package = "SAShiny"
#' ))
#' # Without a licence acknowledgement nothing is sent to 'SAS': the run
#' # returns an error result immediately.
#' engine <- sas_connect(sas_viya("https://viya.example.com"), license_ack = FALSE)
#' result <- sas_engine_run(engine, contract, list())
#' result$status
#' result$metadata$engine_error
#' \dontrun{
#' # Needs a licensed 'SAS Viya' server and saspy; not run during checks.
#' engine <- sas_connect(sas_viya("https://viya.example.com"), license_ack = TRUE)
#' result <- sas_engine_run(engine, contract, list())
#' }
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

#' Close an engine (extension generic)
#'
#' The S3 generic behind [sas_close()]: engine classes implement a method to
#' end their 'SAS' sessions. Users call [sas_close()].
#'
#' @param engine An engine object.
#' @return Invisibly, `NULL`.
#' @keywords internal
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
  .sashiny_result(run_id, "error", metadata = meta)
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

#' Stop unless `engine` is a supported engine (spec section 6.6).
#'
#' The public entry points accept the saspy engine, pools (a pool checks each
#' engine its factory makes), the replay engine (`sas_replay()`, which replays
#' only recordings with provenance from a licensed 'SAS' run) and engines of a
#' class registered with `sas_register_engine()`. Any other engine class (the
#' internal mock, or an unregistered class that could return logs that never
#' came from 'SAS') is accepted only inside the package's own test suite.
#' @param engine An engine object.
#' @return Invisibly, `engine`.
#' @noRd
.sashiny_check_engine <- function(engine) {
  builtin <- c("sashiny_engine_saspy", "sashiny_pool", "sashiny_engine_replay")
  registered <- names(.sashiny_registry$engines)
  if (inherits(engine, c(builtin, registered)) || .sashiny_testing()) {
    return(invisible(engine))
  }
  .sashiny_abort("engine",
    "engine must come from sas_connect(), sas_engine_saspy(), sas_pool() or sas_replay(), ",
    "or be of a class registered with sas_register_engine(): ",
    "SAShiny runs programs only on a live 'SAS' 9.4, 'SAS Viya' or ",
    "'SAS OnDemand for Academics' system, or replays recordings of such runs")
}
