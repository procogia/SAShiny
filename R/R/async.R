# Non-blocking engine runs for the Shiny module (issue #44; PLAN.md section 5.1).
#
# A saspy submission blocks the R process, so a run inside the Shiny process
# would freeze every other browser session. In a running app the module runs
# the engine in a `callr` background R process (which loads the installed
# SAShiny) and polls it with `later`, so the event loop stays free.

#' A copy of an engine that can be sent to a background R process, or NULL.
#'
#' Only the saspy engine (and the internal test mock) are portable. A saspy engine's live
#' session is an external pointer that cannot be serialised, so the child gets
#' a fresh engine with the same configuration; it starts its own session and
#' ends it when the run finishes (as the deadline process already does). A
#' pool owns live sessions and shared state, and a custom engine class may have
#' methods or state the child cannot see, so both return NULL (run in-process).
#' @param engine An engine object.
#' @return A portable engine, or `NULL`.
#' @noRd
.sashiny_portable_engine <- function(engine) {
  if (identical(class(engine)[[1]], "sashiny_engine_mock")) {
    return(engine)
  }
  if (identical(class(engine)[[1]], "sashiny_engine_saspy")) {
    # The child has its own options, so the licence acknowledgement is
    # resolved here and passed on explicitly.
    return(.sashiny_new_saspy_engine(engine$cfg,
      cfgname = engine$cfgname, session_factory = engine$session_factory,
      license_ack = .sashiny_license_ok(engine), backend = engine$backend
    ))
  }
  NULL
}

#' The whole-run deadline of a saspy run, in seconds (spec sections 2.3, 6.5).
#'
#' Mirrors `sas_engine_run.sashiny_engine_saspy()`: an explicit
#' `run.timeout_seconds` always applies; otherwise the 300 second default
#' applies except to the in-process testing hook (`session_factory`). Other
#' engines have no deadline.
#' @param engine An engine object.
#' @param contract A `sashiny_contract` object.
#' @return The deadline in seconds, or `Inf`.
#' @noRd
.sashiny_run_deadline <- function(engine, contract) {
  if (!inherits(engine, "sashiny_engine_saspy")) {
    return(Inf)
  }
  run <- contract$data$run %||% list()
  if (is.null(run$timeout_seconds) && !is.null(engine$session_factory)) {
    return(Inf)
  }
  as.numeric(run$timeout_seconds %||% 300)
}

#' The body of a background run, evaluated in the `callr` child.
#'
#' `callr` sets this function's environment to the SAShiny namespace in the
#' child. A saspy run calls the synchronous body directly: re-entering
#' [sas_engine_run()] would start the deadline process again (issue #97). The
#' deadline is enforced by the parent instead, which kills this process.
#' @param args The run arguments.
#' @return A `sashiny_result`.
#' @noRd
.sashiny_bg_child <- function(args) {
  engine <- args$engine
  if (inherits(engine, "sashiny_engine_saspy")) {
    on.exit(sas_engine_close(engine), add = TRUE)
    return(.sashiny_run_saspy(engine, args$contract, args$values, args$today, args$uploads,
      args$run_id, .sashiny_now(), Sys.time()))
  }
  sas_engine_run(engine, args$contract, args$values,
    today = args$today, uploads = args$uploads, run_id = args$run_id
  )
}

#' Run an engine in a background process and return a promise of its result.
#'
#' Starts the run in a `callr::r_bg()` child that loads the installed SAShiny,
#' then polls it with `later::later()`. The promise resolves with the
#' `sashiny_result`, or with an error result when the saspy deadline passes
#' (the child, and so its SAS session, is killed; spec section 6.5). It
#' rejects when the child fails or is killed for another reason.
#' @param engine A portable engine (see `.sashiny_portable_engine()`).
#' @param contract A `sashiny_contract` object.
#' @param values Input values.
#' @param uploads Dataset uploads.
#' @param today A `Date` used to resolve `"today"`.
#' @param run_id The run id, or `NULL` for a new one.
#' @param poll Seconds between checks of the child process.
#' @param session A Shiny session whose end kills the run, or `NULL`.
#' @return A `promises::promise`.
#' @noRd
.sashiny_run_bg_promise <- function(engine, contract, values, uploads = NULL, today = Sys.Date(),
                                    run_id = NULL, poll = 0.05, session = NULL) {
  .sashiny_need("callr", "to run SAS without blocking the app")
  .sashiny_need("later", "to run SAS without blocking the app")
  .sashiny_need("promises", "to run SAS without blocking the app")
  run_id <- run_id %||% .sashiny_run_id()
  deadline <- .sashiny_run_deadline(engine, contract)
  args <- list(
    engine = engine, contract = contract, values = values, uploads = uploads,
    today = today, run_id = run_id
  )
  # CRAN: a supervised child R session, started only from a running Shiny app;
  # killed on timeout or when the browser session ends.
  proc <- callr::r_bg(.sashiny_bg_child, args = list(args), package = "SAShiny", supervise = TRUE)
  forget <- function() NULL
  if (!is.null(session)) {
    forget <- session$onSessionEnded(function() if (proc$is_alive()) proc$kill())
  }
  t0 <- Sys.time()
  promises::promise(function(resolve, reject) {
    check <- function() {
      if (proc$is_alive()) {
        elapsed <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
        if (elapsed > deadline) {
          proc$kill()
          if (is.function(forget)) forget()
          resolve(.sashiny_engine_error(run_id, list(engine = "saspy"),
            simpleError(sprintf("run exceeded timeout_seconds=%g", deadline))))
          return(invisible())
        }
        later::later(check, poll)
        return(invisible())
      }
      if (is.function(forget)) forget()
      result <- tryCatch(proc$get_result(), error = function(e) e)
      if (inherits(result, "error")) reject(result) else resolve(result)
      invisible()
    }
    check()
  })
}
