# Runner for SAShiny.
#
# The runner is a thin orchestration over an engine: it loads a contract,
# validates and renders the inputs, submits the wrapper, and collects the
# outputs into a `sashiny_result`. It is the layer the Shiny modules and app
# helpers call.

#' Run a contract with the given inputs on an engine
#'
#' @param contract A `sashiny_contract` object, or a path to a `*.sashiny.yml`
#'   file (loaded automatically).
#' @param values A named list of input values.
#' @param engine An engine from [sas_connect()], [sas_engine_saspy()] or
#'   [sas_pool()].
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to a file path, a
#'   Shiny `fileInput` value, or `TRUE` for the input's `sample`.
#' @param run_id The run identifier.
#' @return A `sashiny_result` object (see [sas_engine_run()]).
#' @examples
#' path <- system.file("examples", "minimal", "minimal.sashiny.yml", package = "SAShiny")
#' \dontrun{
#' # Needs a licensed 'SAS' system and saspy; not run during checks.
#' engine <- sas_connect("sas94", host = "sas.example.com", license_ack = TRUE)
#' result <- sas_run(path, list(), engine)
#' result$status
#' sas_engine_close(engine)
#' }
#' @export
sas_run <- function(contract, values, engine, today = Sys.Date(),
                    uploads = NULL, run_id = NULL) {
  .sashiny_check_engine(engine)
  if (!inherits(contract, "sashiny_contract")) {
    contract <- sas_contract(contract)
  }
  sas_engine_run(engine, contract, values,
    today = today,
    uploads = uploads, run_id = run_id
  )
}
