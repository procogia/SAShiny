# Run result object for SAShiny.
#
# Implements spec/CONTRACT.md section 8: the collected outputs of a run plus its
# metadata. A `sashiny_result` is produced by an engine's run method and carries
# the run metadata required by the spec (run_id, contract/program hashes,
# rendered macros, timestamps, engine/SAS version, status).

#' Create a run result object
#'
#' @param run_id The run identifier (spec section 6.1).
#' @param status `success`, `warning` or `error` (spec section 6.5).
#' @param outputs A named list of collected outputs keyed by output id. Each
#'   value is the language-neutral value of spec section 8.1 (tables, plots,
#'   HTML, log lines and base64 downloads), or `list(error = message)` when
#'   that output could not be collected.
#' @param log The full main-submission log text.
#' @param metadata A named list of run metadata.
#' @return A `sashiny_result` object (a named list).
#' @export
sashiny_result <- function(run_id, status, outputs = list(), log = "",
                           metadata = list()) {
  structure(
    list(
      run_id = run_id, status = status, outputs = outputs, log = log,
      metadata = metadata
    ),
    class = "sashiny_result"
  )
}

#' Build the standard run metadata
#'
#' @param run_id The run identifier.
#' @param status The run status.
#' @param contract_sha256 SHA-256 of the contract YAML bytes.
#' @param program_sha256 SHA-256 of the program file bytes.
#' @param macros A named list of rendered macro values.
#' @param engine Engine name.
#' @param engine_version Engine version.
#' @param sas_version SAS version (`&SYSVLONG`).
#' @param started_at Start timestamp (UTC, ISO 8601).
#' @param ended_at End timestamp (UTC, ISO 8601).
#' @return A named list of metadata.
#' @noRd
.sashiny_metadata <- function(run_id, status, contract_sha256 = "",
                              program_sha256 = "", macros = list(),
                              engine = "", engine_version = "",
                              sas_version = "", started_at = NULL,
                              ended_at = NULL) {
  started_at <- started_at %||% .sashiny_now()
  ended_at <- ended_at %||% .sashiny_now()
  list(
    run_id = run_id,
    contract_sha256 = contract_sha256,
    program_sha256 = program_sha256,
    macros = macros,
    started_at = started_at,
    ended_at = ended_at,
    engine = engine,
    engine_version = engine_version,
    sas_version = sas_version,
    status = status,
    collect_errors = list()
  )
}
