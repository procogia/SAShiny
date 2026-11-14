# Bounded SAS session pool for SAShiny.
#
# Implements a bounded pool of engine sessions (issue #7). The pool reuses
# sessions up to `max_runs_per_session`, discards sessions whose run failed in
# SAS, and enforces `max_size`/`idle_timeout` bounds. A pool is itself an
# engine: pass it anywhere an engine is accepted.

#' Create a bounded session pool
#'
#' @param engine An engine factory (a function with no arguments, such as
#'   `function() sas_connect("oda")`), giving each pooled session its own SAS
#'   session; or a single engine shared by all pooled sessions (suitable for
#'   [sas_engine_mock()]).
#' @param min_size Minimum number of sessions kept warm.
#' @param max_size Maximum number of concurrent sessions.
#' @param idle_timeout Seconds after which an idle session is discarded.
#' @param max_runs_per_session Runs before a session is discarded and replaced.
#' @param acquire_timeout Seconds to wait for a free session when every session
#'   is busy before reporting `pool exhausted` (spec section 6.5).
#' @return A `sashiny_pool` object (an environment).
#' @examples
#' pool <- sas_pool(sas_engine_mock(), max_size = 2L)
#' sas_pool_close(pool)
#' @export
sas_pool <- function(engine, min_size = 0L, max_size = 4L,
                     idle_timeout = 300, max_runs_per_session = 100L,
                     acquire_timeout = 30) {
  if (min_size < 0L || max_size < 0L) {
    stop("min_size and max_size must be non-negative", call. = FALSE)
  }
  if (min_size > max_size) {
    stop("min_size must not exceed max_size", call. = FALSE)
  }
  # Session counts are discrete: a fractional maximum would admit one more
  # session than configured (spec §6.5 bounds the pool).
  if (!.sashiny_is_int(min_size) || !.sashiny_is_int(max_size)) {
    stop("min_size and max_size must be whole numbers", call. = FALSE)
  }
  if (!is.finite(acquire_timeout) || acquire_timeout < 0) {
    stop("acquire_timeout must be a non-negative finite number", call. = FALSE)
  }
  pool <- new.env(parent = emptyenv())
  if (is.function(engine)) {
    pool$engine <- NULL
    pool$factory <- engine
  } else {
    pool$engine <- engine
    pool$factory <- NULL
  }
  pool$min_size <- min_size
  pool$max_size <- max_size
  pool$idle_timeout <- idle_timeout
  pool$max_runs_per_session <- max_runs_per_session
  pool$acquire_timeout <- acquire_timeout
  pool$sessions <- list()
    pool$closed <- FALSE
  class(pool) <- c("sashiny_pool", "sashiny_engine")
  .sashiny_top_up(pool)
  pool
}

#' Create sessions until the warm minimum `min_size` is met.
#' @noRd
.sashiny_top_up <- function(pool) {
  if (isTRUE(pool$closed)) {
    return(invisible(NULL))
  }
  while (length(pool$sessions) < pool$min_size) {
    s <- .sashiny_new_session(pool)
    pool$sessions[[length(pool$sessions) + 1L]] <- s
  }
  invisible(NULL)
}

#' Create a new pooled session.
#' @noRd
.sashiny_new_session <- function(pool) {
  s <- new.env(parent = emptyenv())
  s$engine <- if (is.null(pool$factory)) pool$engine else pool$factory()
  s$session_id <- .sashiny_run_id()
  s$runs <- 0L
  s$last_used <- as.numeric(Sys.time())
  s$in_use <- FALSE
  s
}

#' Close a factory-made session's engine (a shared engine stays open).
#' @noRd
.sashiny_close_session <- function(pool, session) {
  if (!is.null(pool$factory)) {
    try(sas_engine_close(session$engine), silent = TRUE)
  }
}

#' Acquire a session from the pool.
#'
#' Waits up to `pool$acquire_timeout` seconds for a free session when every
#' session is busy, then returns `NULL` (the caller reports `pool exhausted`).
#' @noRd
.sashiny_acquire <- function(pool) {
  deadline <- as.numeric(Sys.time()) + pool$acquire_timeout
  repeat {
    if (isTRUE(pool$closed)) {
      return(NULL)
    }
    now <- as.numeric(Sys.time())
    expired <- vapply(pool$sessions, function(s) {
      !s$in_use && (now - s$last_used) >= pool$idle_timeout
    }, logical(1))
    idle <- pool$sessions[expired]
    pool$sessions <- pool$sessions[!expired]
    for (s in idle) .sashiny_close_session(pool, s)
    .sashiny_top_up(pool)
    for (s in pool$sessions) {
      if (!s$in_use) {
        s$in_use <- TRUE
        s$last_used <- now
        return(s)
      }
    }
    if (length(pool$sessions) < pool$max_size) {
      s <- .sashiny_new_session(pool)
      s$in_use <- TRUE
      pool$sessions[[length(pool$sessions) + 1L]] <- s
      return(s)
    }
    # Every session is busy: wait for a release (spec section 6.5).
    if (as.numeric(Sys.time()) >= deadline) {
      return(NULL)
    }
    Sys.sleep(0.05)
  }
}

#' Release a session back to the pool.
#' @noRd
.sashiny_release <- function(pool, session, discard = FALSE) {
  session$in_use <- FALSE
  session$last_used <- as.numeric(Sys.time())
  if (discard || session$runs >= pool$max_runs_per_session) {
    pool$sessions <- Filter(function(s) !identical(s, session), pool$sessions)
    .sashiny_close_session(pool, session)
  }
  .sashiny_top_up(pool)
}

#' @export
sas_engine_run.sashiny_pool <- function(engine, contract, values, today = Sys.Date(),
                                        uploads = NULL, run_id = NULL) {
  pool <- engine
  run_id <- run_id %||% .sashiny_run_id()
  session <- .sashiny_acquire(pool)
  if (is.null(session)) {
    return(.sashiny_engine_error(
      run_id, list(engine = "pool"),
      simpleError(sprintf("pool exhausted: all %d sessions busy", pool$max_size))
    ))
  }
  discard <- FALSE
  result <- tryCatch(
    sas_engine_run(session$engine, contract, values,
      today = today, uploads = uploads, run_id = run_id
    ),
    error = function(e) {
      discard <<- TRUE
      .sashiny_engine_error(run_id, list(engine = "pool"), e)
    }
  )
  session$runs <- session$runs + 1L
  # Input validation errors never reach SAS, so the session stays usable.
  if (identical(result$status, "error") && is.null(result$metadata$issues)) {
    discard <- TRUE
  }
  .sashiny_release(pool, session, discard = discard)
  result
}

#' @export
sas_engine_choices.sashiny_pool <- function(engine, contract) {
  session <- .sashiny_acquire(engine)
  if (is.null(session)) {
    stop(sprintf("pool exhausted: all %d sessions busy", engine$max_size), call. = FALSE)
  }
  on.exit(.sashiny_release(engine, session), add = TRUE)
  sas_engine_choices(session$engine, contract)
}

#' @export
sas_engine_close.sashiny_pool <- function(engine) {
  engine$closed <- TRUE
  sessions <- engine$sessions
  engine$sessions <- list()
  for (s in sessions) .sashiny_close_session(engine, s)
  invisible(NULL)
}

#' Run a contract on a pooled session
#'
#' Equivalent to [sas_engine_run()] on the pool. The session is discarded if a
#' submitted run errors (spec section 6.5); input validation errors keep it.
#'
#' @inheritParams sas_engine_run
#' @param pool A `sashiny_pool` object.
#' @return A `sashiny_result` object.
#' @export
sas_pool_run <- function(pool, contract, values, today = Sys.Date(),
                         uploads = NULL, run_id = NULL) {
  sas_engine_run(pool, contract, values, today = today, uploads = uploads, run_id = run_id)
}

#' Close a pool, ending every pooled session
#'
#' @param pool A `sashiny_pool` object.
#' @return Invisibly, `NULL`.
#' @export
sas_pool_close <- function(pool) {
  sas_engine_close(pool)
}
