# Runner for SAShiny.
#
# The runner is a thin orchestration over an engine: it loads a contract,
# validates and renders the inputs, submits the wrapper, and collects the
# outputs into a `sashiny_result`. It is the layer the Shiny modules and app
# helpers call, and it is fully testable against the mock engine.

#' Run a contract with the given inputs on an engine
#'
#' @param contract A `sashiny_contract` object, or a path to a `*.sashiny.yml`
#'   file (loaded automatically).
#' @param values A named list of input values.
#' @param engine An engine object (e.g. from [sas_engine_mock()]).
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to `TRUE`.
#' @param run_id The run identifier.
#' @return A `sashiny_result` object.
#' @examples
#' dir <- tempfile("sashiny-")
#' dir.create(dir)
#' writeLines(c(
#'   "sashiny: 1",
#'   "program: program.sas",
#'   "title: Minimal",
#'   "outputs:",
#'   "  log:",
#'   "    type: log"
#' ), file.path(dir, "contract.sashiny.yml"))
#' writeLines("proc print data=sashelp.class; run;", file.path(dir, "program.sas"))
#' result <- sas_run(file.path(dir, "contract.sashiny.yml"), list(), sas_engine_mock())
#' result$status
#' @export
sas_run <- function(contract, values, engine, today = Sys.Date(),
                    uploads = NULL, run_id = NULL) {
  if (!inherits(contract, "sashiny_contract")) {
    contract <- sas_contract(contract)
  }
  sas_engine_run(engine, contract, values,
    today = today,
    uploads = uploads, run_id = run_id
  )
}
