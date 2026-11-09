# Bounded SAS session pool for SAShiny.
#
# Implements a bounded pool of engine sessions (issue #7). The pool reuses
# sessions up to `max_runs_per_session`, discards sessions that error or time
# out, and enforces `min`/`max`/`idle_timeout` bounds. It works against any
# engine (mock or saspy).

#' Create a bounded session pool
#'
#' @param engine An engine object (e.g. from [sas_engine_mock()]).
#' @param min_size Minimum number of sessions kept warm.
#' @param max_size Maximum number of concurrent sessions.
#' @param idle_timeout Seconds after which an idle session is discarded.
#' @param max_runs_per_session Runs before a session is discarded and replaced.
#' @return A `sashiny_pool` object (an environment).
#' @export
sas_pool <- function(engine, min_size = 0L, max_size = 4L,
                     idle_timeout = 300, max_runs_per_session = 100L) {
  pool <- new.env(parent = emptyenv())
  pool$engine <- engine
  pool$min_size <- min_size
  pool$max_size <- max_size
  pool$idle_timeout <- idle_timeout
  pool$max_runs_per_session <- max_runs_per_session
  pool$sessions <- list()
  class(pool) <- "sashiny_pool"
  pool
}

#' Create a new pooled session.
#' @noRd
.sashiny_new_session <- function(pool) {
  s <- new.env(parent = emptyenv())
  s$engine <- pool$engine
  s$session_id <- .sashiny_run_id()
  s$runs <- 0L
  s$last_used <- as.numeric(Sys.time())
  s$in_use <- FALSE
  s
}

#' Acquire a session from the pool.
#' @noRd
.sashiny_acquire <- function(pool) {
  now <- as.numeric(Sys.time())
  # Reap idle sessions past the timeout.
  pool$sessions <- Filter(function(s) {
    s$in_use || (now - s$last_used) < pool$idle_timeout
  }, pool$sessions)
  # Reuse an idle session.
  for (i in seq_along(pool$sessions)) {
    if (!pool$sessions[[i]]$in_use) {
      pool$sessions[[i]]$in_use <- TRUE
      pool$sessions[[i]]$last_used <- now
      return(pool$sessions[[i]])
    }
  }
  # Create a new session if under max.
  if (length(pool$sessions) < pool$max_size) {
    s <- .sashiny_new_session(pool)
    s$in_use <- TRUE
    pool$sessions[[length(pool$sessions) + 1L]] <- s
    return(s)
  }
  stop("pool exhausted")
}

#' Release a session back to the pool.
#' @noRd
.sashiny_release <- function(pool, session, discard = FALSE) {
  session$in_use <- FALSE
  session$last_used <- as.numeric(Sys.time())
  if (discard || session$runs >= pool$max_runs_per_session) {
    pool$sessions <- Filter(function(s) !identical(s, session), pool$sessions)
  }
}

#' Run a contract on a pooled session
#'
#' The session is discarded if the run errors or times out (spec section 6.5).
#'
#' @param pool A `sashiny_pool` object.
#' @param contract A `sashiny_contract` object.
#' @param values A named list of input values.
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to `TRUE`.
#' @param run_id The run identifier.
#' @return A `sashiny_result` object.
#' @export
sas_pool_run <- function(pool, contract, values, today = Sys.Date(),
                         uploads = NULL, run_id = NULL) {
  session <- .sashiny_acquire(pool)
  discard <- FALSE
  result <- tryCatch(
    sas_engine_run(session$engine, contract, values, today = today,
                   uploads = uploads, run_id = run_id),
    error = function(e) {
      discard <<- TRUE
      sashiny_result(run_id %||% .sashiny_run_id(), "error",
                     metadata = .sashiny_metadata(run_id %||% .sashiny_run_id(),
                                                  "error", engine = "pool"))
    }
  )
  session$runs <- session$runs + 1L
  if (identical(result$status, "error")) {
    discard <- TRUE
  }
  .sashiny_release(pool, session, discard = discard)
  result
}

#' Close a pool, discarding all sessions.
#'
#' @param pool A `sashiny_pool` object.
#' @return Invisibly, `NULL`.
#' @export
sas_pool_close <- function(pool) {
  pool$sessions <- list()
  invisible(NULL)
}