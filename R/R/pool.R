# Bounded SAS session pool for SAShiny.
#
# Implements a bounded pool of engine sessions (issue #7). The pool reuses
# sessions up to `max_runs_per_session`, discards sessions whose run failed in
# SAS, and enforces `max_size`/`idle_timeout` bounds. A pool is itself an
# engine: pass it anywhere an engine is accepted.

#' Create a bounded session pool
#'
#' @param engine An engine factory: a function with no arguments returning a
#'   [sas_connect()] engine, such as `function() sas_connect("oda")`. Each
#'   pooled session gets its own 'SAS' session. A single engine is also
#'   accepted and is then shared by all pooled sessions.
#' @param min_size Minimum number of sessions kept warm.
#' @param max_size Maximum number of concurrent sessions.
#' @param idle_timeout Seconds after which an idle session is discarded.
#' @param max_runs_per_session Runs before a session is discarded and replaced.
#' @param acquire_timeout Seconds to wait for a free session when every session
#'   is busy before reporting `pool exhausted` (spec section 6.5).
#' @return A `sashiny_pool` object (an environment).
#' @examples
#' # With min_size = 0 creating a pool starts no 'SAS' session.
#' pool <- sas_pool(function() sas_connect("oda", region = "us1"), max_size = 2L)
#' sas_close(pool)
#' @export
sas_pool <- function(engine, min_size = 0L, max_size = 4L,
                     idle_timeout = 300, max_runs_per_session = 100L,
                     acquire_timeout = 30) {
  if (min_size < 0L || max_size < 0L) {
    .sashiny_abort("engine", "min_size and max_size must be non-negative")
  }
  if (min_size > max_size) {
    .sashiny_abort("engine", "min_size must not exceed max_size")
  }
  # Session counts are discrete: a fractional maximum would admit one more
  # session than configured (spec section 6.5 bounds the pool).
  if (!.sashiny_is_int(min_size) || !.sashiny_is_int(max_size)) {
    .sashiny_abort("engine", "min_size and max_size must be whole numbers")
  }
  if (!is.finite(acquire_timeout) || acquire_timeout < 0) {
    .sashiny_abort("engine", "acquire_timeout must be a non-negative finite number")
  }
  if (!is.function(engine)) .sashiny_check_engine(engine)
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
  s$engine <- if (is.null(pool$factory)) pool$engine else .sashiny_check_engine(pool$factory())
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
    s <- .sashiny_try_acquire(pool)
    if (!is.null(s) || isTRUE(pool$closed)) {
      return(s)
    }
    # Every session is busy: wait for a release (spec section 6.5).
    if (as.numeric(Sys.time()) >= deadline) {
      return(NULL)
    }
    Sys.sleep(0.05)
  }
}

#' One acquisition attempt: a free (or new) session, or NULL when all are busy.
#' @noRd
.sashiny_try_acquire <- function(pool) {
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
  NULL
}

#' Release a session back to the pool.
#' @noRd
.sashiny_release <- function(pool, session, discard = FALSE) {
  session$in_use <- FALSE
  session$last_used <- as.numeric(Sys.time())
  if (discard) .sashiny_clear_choices(pool) # spec section 6.4: a session was replaced
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
  # A lazy factory/connection failure during acquisition must become an error
  # result, not escape (issue #75).
  session <- tryCatch(
    .sashiny_acquire(pool),
    error = function(e) {
      return(.sashiny_engine_error(run_id, list(engine = "pool"), e))
    }
  )
  if (inherits(session, "sashiny_result")) {
    return(session)
  }
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

#' Run on a pool without blocking the event loop (spec section 6.5).
#'
#' Acquires a free session with `later` polling (never `Sys.sleep()` on the
#' event loop) up to `acquire_timeout`, then runs on that session's engine
#' through `.sashiny_run_async()`. "pool exhausted" resolves as an error result.
#' @noRd
.sashiny_pool_promise <- function(pool, contract, values, uploads, today, run_id, session) {
  deadline <- as.numeric(Sys.time()) + pool$acquire_timeout
  acquire <- function() {
    promises::promise(function(resolve, reject) {
      try_once <- function() {
        got <- tryCatch(.sashiny_try_acquire(pool), error = function(e) e)
        if (inherits(got, "error")) {
          return(resolve(.sashiny_engine_error(run_id, list(engine = "pool"), got)))
        }
        if (!is.null(got) || isTRUE(pool$closed) || as.numeric(Sys.time()) >= deadline) {
          return(resolve(got))
        }
        later::later(try_once, 0.05)
      }
      try_once()
    })
  }
  promises::then(acquire(), function(s) {
    if (inherits(s, "sashiny_result")) {
      return(s)
    }
    if (is.null(s)) {
      return(.sashiny_engine_error(run_id, list(engine = "pool"),
        simpleError(sprintf("pool exhausted: all %d sessions busy", pool$max_size))))
    }
    p <- .sashiny_run_async(s$engine, contract, values, uploads, today, run_id, session)
    p <- promises::then(p, function(result) {
      s$runs <- s$runs + 1L
      discard <- identical(result$status, "error") && is.null(result$metadata$issues)
      .sashiny_release(pool, s, discard = discard)
      result
    })
    promises::catch(p, function(e) {
      .sashiny_release(pool, s, discard = TRUE)
      .sashiny_engine_error(run_id, list(engine = "pool"), e)
    })
  })
}

#' @export
sas_engine_choices.sashiny_pool <- function(engine, contract) {
  session <- .sashiny_acquire(engine)
  if (is.null(session)) {
    .sashiny_abort("engine", sprintf("pool exhausted: all %d sessions busy", engine$max_size))
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

#' Deprecated pool helpers
#'
#' `sas_pool_run()` is [sas_run()] on a pool and `sas_pool_close()` is
#' [sas_close()]. They still work, with a deprecation warning.
#'
#' @inheritParams sas_engine_run
#' @param pool A `sashiny_pool` object.
#' @return `sas_pool_run()`: a `sashiny_result`. `sas_pool_close()`:
#'   invisibly, `NULL`.
#' @keywords internal
#' @export
sas_pool_run <- function(pool, contract, values, today = Sys.Date(),
                         uploads = NULL, run_id = NULL) {
  lifecycle::deprecate_soft("0.3.1", "sas_pool_run()", "sas_run()")
  sas_engine_run(pool, contract, values, today = today, uploads = uploads, run_id = run_id)
}

#' @rdname sas_pool_run
#' @export
sas_pool_close <- function(pool) {
  lifecycle::deprecate_soft("0.3.1", "sas_pool_close()", "sas_close()")
  sas_engine_close(pool)
}
