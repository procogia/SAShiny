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
#' @param engine An engine from [sas_connect()], [sas_engine_saspy()] or
#'   [sas_pool()].
#' @param values A named list of input values. Defaults to the contract's
#'   defaults (an empty list).
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to a file path, a
#'   Shiny `fileInput` value, or `TRUE` for the input's `sample`.
#' @param run_id The run identifier.
#' @return A `sashiny_result` object (see [sas_engine_run()]).
#' @section Argument order:
#' Before 'SAShiny' 0.3.1 the order was `sas_run(contract, values, engine)`.
#' That order still works, with a deprecation warning.
#' @examples
#' path <- system.file("examples", "minimal", "minimal.sashiny.yml", package = "SAShiny")
#' \dontrun{
#' # Needs a licensed 'SAS' system and saspy; not run during checks.
#' engine <- sas_connect(sas_94_iom("sas.example.com"), license_ack = TRUE)
#' result <- sas_run(path, engine)
#' result$status
#' sas_close(engine)
#' }
#' @export
sas_run <- function(contract, engine, values = list(), today = Sys.Date(),
                    uploads = NULL, run_id = NULL) {
  # Old order: sas_run(contract, values, engine). Detect it by class.
  if (!inherits(engine, "sashiny_engine") && inherits(values, "sashiny_engine")) {
    lifecycle::deprecate_soft("0.3.1", "sas_run(values)",
      details = "Pass the engine second: `sas_run(contract, engine, values)`."
    )
    swap <- engine
    engine <- values
    values <- swap
  }
  .sashiny_check_engine(engine)
  if (!inherits(contract, "sashiny_contract")) {
    contract <- sas_contract(contract)
  }
  values <- values %||% list()
  # Opt-in result cache (spec section 6.11); a no-op unless `run.cache: true`.
  .sashiny_cached_run(engine, contract, values,
    function() sas_engine_run(engine, contract, values, today = today, uploads = uploads,
      run_id = run_id),
    today = today, uploads = uploads
  )
}

#' Close an engine or a pool
#'
#' Ends every 'SAS' session the engine or pool holds (and its worker
#' processes). Safe to call more than once.
#'
#' @param engine An engine from [sas_connect()] or a pool from [sas_pool()].
#' @return Invisibly, `NULL`.
#' @examples
#' pool <- sas_pool(function() sas_connect(sas_oda("us1")), max_size = 2L)
#' sas_close(pool)
#' @export
sas_close <- function(engine) {
  sas_engine_close(engine)
}
