# Persistent SAS workers (spec section 6.5, "Session lifetime"; #130 J1/J2).
#
# A saspy submission blocks the R process and cannot be interrupted. Each
# saspy engine therefore runs its SAS session in one long-lived child R
# process (a `callr::r_session`). The child keeps the engine, and so the SAS
# session, between runs. A run is a call into that child:
# - synchronously, it waits up to `run.timeout_seconds`;
# - in a Shiny app, a promise polls the child with `later`, so the event loop
#   stays free.
# On timeout or session end the child is killed (its SAS session dies with it)
# and the next run starts a new one lazily.
#
# CRAN: the child process starts only when a live 'SAS' run is requested (or
# in tests that opt in); it is supervised and never started during
# 'R CMD check' examples.

# Inside a worker child process: the engine (and so the SAS session) that the
# child keeps between calls. Holding it in a package environment, not the
# global environment, keeps the child's workspace untouched.
.sashiny_worker_state <- new.env(parent = emptyenv())

#' Whether an engine runs through its persistent worker.
#'
#' Real saspy engines always do. The in-process testing hook (a fake session
#' factory) stays in-process so tests can observe it, unless the contract sets
#' an explicit `run.timeout_seconds` (which must be able to kill the session)
#' or the test asks for the worker with `engine$use_worker <- TRUE`.
#' @param engine A `sashiny_engine_saspy`.
#' @param contract A `sashiny_contract`.
#' @return `TRUE` or `FALSE`.
#' @noRd
.sashiny_uses_worker <- function(engine, contract) {
  if (isTRUE(engine$in_worker)) {
    return(FALSE)
  }
  if (isTRUE(engine$use_worker) || is.null(engine$session_factory)) {
    return(TRUE)
  }
  !is.null((contract$data$run %||% list())$timeout_seconds)
}

#' The whole-run deadline in seconds (spec sections 2.3, 6.5).
#' @noRd
.sashiny_run_deadline <- function(contract) {
  as.numeric((contract$data$run %||% list())$timeout_seconds %||% 300)
}

#' The engine's worker state, created on first use.
#' @noRd
.sashiny_worker <- function(engine) {
  if (is.null(engine$worker)) {
    w <- new.env(parent = emptyenv())
    w$rs <- NULL
    w$id <- NULL
    w$busy <- FALSE
    w$starts <- 0L
    engine$worker <- w
  }
  engine$worker
}

#' Start the worker's child process and create the engine inside it.
#' @noRd
.sashiny_worker_start <- function(engine) {
  w <- .sashiny_worker(engine)
  if (!is.null(w$rs) && w$rs$is_alive()) {
    return(w)
  }
  rs <- callr::r_session$new(wait = TRUE, options = callr::r_session_options(supervise = TRUE))
  args <- list(
    cfg = engine$cfg, cfgname = engine$cfgname, backend = engine$backend,
    license_ack = .sashiny_license_ok(engine), session_factory = engine$session_factory
  )
  rs$run(function(args) {
    new_engine <- utils::getFromNamespace(".sashiny_new_saspy_engine", "SAShiny")
    engine <- new_engine(args$cfg,
      cfgname = args$cfgname, session_factory = args$session_factory,
      license_ack = args$license_ack, backend = args$backend
    )
    # Inside the worker the engine owns the SAS session directly (no nested worker).
    engine$in_worker <- TRUE
    state <- utils::getFromNamespace(".sashiny_worker_state", "SAShiny")
    state$engine <- engine
    invisible(NULL)
  }, list(args))
  w$rs <- rs
  w$id <- .sashiny_run_id()
  w$starts <- w$starts + 1L
  w
}

#' Kill the worker; its SAS session dies with it (spec section 6.5).
#' @noRd
.sashiny_worker_kill <- function(engine) {
  w <- engine$worker
  if (is.null(w)) {
    return(invisible(NULL))
  }
  if (!is.null(w$rs)) try(w$rs$kill(), silent = TRUE)
  w$rs <- NULL
  w$id <- NULL
  w$busy <- FALSE
  invisible(NULL)
}

#' End the worker cleanly: close the SAS session in the child, then the child.
#' @noRd
.sashiny_worker_close <- function(engine) {
  w <- engine$worker
  if (is.null(w) || is.null(w$rs)) {
    return(invisible(NULL))
  }
  if (!w$busy && w$rs$is_alive()) {
    try(w$rs$run(function() {
      e <- utils::getFromNamespace(".sashiny_worker_state", "SAShiny")$engine
      if (!is.null(e)) SAShiny::sas_engine_close(e)
      invisible(NULL)
    }), silent = TRUE)
    try(w$rs$close(), silent = TRUE)
  }
  .sashiny_worker_kill(engine)
}

#' Start a run in the worker (non-blocking).
#' @noRd
.sashiny_worker_call <- function(engine, contract, values, today, uploads, run_id) {
  w <- .sashiny_worker_start(engine)
  w$busy <- TRUE
  w$rs$call(function(args) {
    engine <- utils::getFromNamespace(".sashiny_worker_state", "SAShiny")$engine
    run_sync <- utils::getFromNamespace(".sashiny_run_saspy", "SAShiny")
    result <- run_sync(engine, args$contract, args$values, args$today, args$uploads,
      args$run_id, args$started, Sys.time())
    result$metadata$worker_id <- args$worker_id
    result
  }, list(list(
    contract = contract, values = values, today = today, uploads = uploads,
    run_id = run_id, started = .sashiny_now(), worker_id = w$id
  )))
  w
}

#' Read a finished call: the result, or an engine-error result.
#' @noRd
.sashiny_worker_read <- function(engine, run_id) {
  w <- engine$worker
  msg <- w$rs$read()
  w$busy <- FALSE
  if (!is.null(msg$error)) {
    # The child failed outside the run body (for example it could not load
    # SAShiny); its state is unknown, so replace it.
    .sashiny_worker_kill(engine)
    return(.sashiny_engine_error(run_id, list(engine = "saspy"), msg$error))
  }
  msg$result
}

#' Wait while another call uses the worker, running `later` callbacks so that
#' call's promise can finish. Returns FALSE when the wait timed out.
#' @noRd
.sashiny_worker_wait_free <- function(engine, timeout) {
  w <- .sashiny_worker(engine)
  deadline <- Sys.time() + timeout
  while (w$busy && Sys.time() < deadline) {
    if (requireNamespace("later", quietly = TRUE)) later::run_now(0.05) else Sys.sleep(0.05)
  }
  !w$busy
}

#' Run on the worker and wait (outside Shiny, or in a non-async context).
#' @noRd
.sashiny_worker_run <- function(engine, contract, values, today, uploads, run_id) {
  timeout <- .sashiny_run_deadline(contract)
  if (!.sashiny_worker_wait_free(engine, 30)) {
    return(.sashiny_engine_error(run_id, list(engine = "saspy"),
      simpleError("engine busy: another run is in progress")))
  }
  w <- tryCatch(.sashiny_worker_call(engine, contract, values, today, uploads, run_id),
    error = function(e) e)
  if (inherits(w, "error")) {
    .sashiny_worker_kill(engine)
    return(.sashiny_engine_error(run_id, list(engine = "saspy"), w))
  }
  state <- w$rs$poll_process(as.integer(timeout * 1000))
  if (!identical(state, "ready")) {
    .sashiny_worker_kill(engine)
    return(.sashiny_engine_error(run_id, list(engine = "saspy"),
      simpleError(sprintf("run exceeded timeout_seconds=%g", timeout))))
  }
  .sashiny_worker_read(engine, run_id)
}

#' Run on the worker and return a promise; the event loop stays free.
#'
#' Waits for the worker to be free, starts the call, then polls with
#' `later::later()`. Resolves with the result, or an error result when the
#' deadline passes (the worker is killed). `session`, a Shiny session, kills
#' the in-flight run when it ends (issue #50).
#' @noRd
.sashiny_worker_promise <- function(engine, contract, values, uploads = NULL,
                                    today = Sys.Date(), run_id = NULL, poll = 0.05,
                                    session = NULL) {
  .sashiny_need("later", "to run SAS without blocking the app")
  .sashiny_need("promises", "to run SAS without blocking the app")
  run_id <- run_id %||% .sashiny_run_id()
  timeout <- .sashiny_run_deadline(contract)
  promises::promise(function(resolve, reject) {
    started <- NULL
    cancelled <- FALSE
    forget <- function() NULL
    if (!is.null(session)) {
      forget <- session$onSessionEnded(function() {
        cancelled <<- TRUE
        if (!is.null(started)) .sashiny_worker_kill(engine)
      })
    }
    finish <- function(value) {
      if (is.function(forget)) forget()
      resolve(value)
    }
    check <- function() {
      if (cancelled) {
        return(finish(.sashiny_engine_error(run_id, list(engine = "saspy"),
          simpleError("run cancelled: the browser session ended"))))
      }
      w <- .sashiny_worker(engine)
      if (is.null(started)) {
        if (w$busy) {
          later::later(check, poll)
          return(invisible())
        }
        call <- tryCatch(.sashiny_worker_call(engine, contract, values, today, uploads, run_id),
          error = function(e) e)
        if (inherits(call, "error")) {
          .sashiny_worker_kill(engine)
          return(finish(.sashiny_engine_error(run_id, list(engine = "saspy"), call)))
        }
        started <<- Sys.time()
      }
      if (is.null(w$rs)) {
        return(finish(.sashiny_engine_error(run_id, list(engine = "saspy"),
          simpleError("the SAS worker stopped"))))
      }
      if (identical(w$rs$poll_process(0L), "ready")) {
        return(finish(.sashiny_worker_read(engine, run_id)))
      }
      if (as.numeric(difftime(Sys.time(), started, units = "secs")) > timeout) {
        .sashiny_worker_kill(engine)
        return(finish(.sashiny_engine_error(run_id, list(engine = "saspy"),
          simpleError(sprintf("run exceeded timeout_seconds=%g", timeout)))))
      }
      later::later(check, poll)
      invisible()
    }
    check()
  })
}

#' Read `choices_from` lists in the worker (spec section 6.4), waiting for it.
#' @noRd
.sashiny_worker_choices <- function(engine, contract) {
  if (!.sashiny_worker_wait_free(engine, 30)) stop("engine busy: another run is in progress", call. = FALSE)
  w <- .sashiny_worker_start(engine)
  w$busy <- TRUE
  w$rs$call(function(contract) {
    engine <- utils::getFromNamespace(".sashiny_worker_state", "SAShiny")$engine
    SAShiny::sas_engine_choices(engine, contract)
  }, list(contract))
  if (!identical(w$rs$poll_process(300000L), "ready")) {
    .sashiny_worker_kill(engine)
    stop("reading choices timed out", call. = FALSE)
  }
  msg <- w$rs$read()
  w$busy <- FALSE
  if (!is.null(msg$error)) stop(conditionMessage(msg$error$parent %||% msg$error), call. = FALSE)
  msg$result
}

#' Run any engine without blocking the event loop (spec section 6.5).
#'
#' saspy engines use their worker; a pool acquires a session without blocking
#' and runs on its engine; other engines (the test mock, custom classes) run
#' in-process, as they hold no SAS session this package can move.
#' @noRd
.sashiny_run_async <- function(engine, contract, values, uploads = NULL, today = Sys.Date(),
                               run_id = NULL, session = NULL) {
  run_id <- run_id %||% .sashiny_run_id()
  if (inherits(engine, "sashiny_pool")) {
    return(.sashiny_pool_promise(engine, contract, values, uploads, today, run_id, session))
  }
  if (inherits(engine, "sashiny_engine_saspy") && .sashiny_uses_worker(engine, contract)) {
    if (!.sashiny_license_ok(engine)) {
      return(promises::promise_resolve(.sashiny_engine_error(run_id, list(engine = "saspy"),
        simpleError(.sashiny_license_message))))
    }
    return(.sashiny_worker_promise(engine, contract, values, uploads, today, run_id,
      session = session))
  }
  promises::promise_resolve(
    sas_engine_run(engine, contract, values, today = today, uploads = uploads, run_id = run_id)
  )
}
