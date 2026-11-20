# `choices_from` cache (spec section 6.4, "Caching"; #130 J3).
#
# Choices are loaded once per engine (an app shares one engine across its
# browser sessions) and contract, and reused for `run.choices_ttl_seconds`.
# The cache lives on the engine or pool environment, so replacing the SAS
# session (engine error, timeout) clears it.

#' The time-to-live of a contract's choices in seconds (spec section 6.4).
#' @noRd
.sashiny_choices_ttl <- function(contract) {
  as.numeric((contract$data$run %||% list())$choices_ttl_seconds %||% 3600)
}

#' Whether a contract has any `choices_from` input.
#' @noRd
.sashiny_has_choices_from <- function(contract) {
  any(vapply(contract$data$inputs %||% list(), function(s) !is.null(s$choices_from), logical(1)))
}

#' The cache environment of an engine (a pool or saspy engine), or NULL when
#' the engine cannot hold one (a plain list such as the test mock).
#' @noRd
.sashiny_choices_store <- function(engine) {
  if (!is.environment(engine)) {
    return(NULL)
  }
  if (is.null(engine$choices_cache)) engine$choices_cache <- new.env(parent = emptyenv())
  engine$choices_cache
}

#' Fresh cached choices for a contract, or NULL.
#' @noRd
.sashiny_cached_choices <- function(engine, contract) {
  store <- .sashiny_choices_store(engine)
  ttl <- .sashiny_choices_ttl(contract)
  key <- .sashiny_contract_sha256(contract)
  if (is.null(store) || ttl <= 0 || !exists(key, envir = store, inherits = FALSE)) {
    return(NULL)
  }
  hit <- get(key, envir = store, inherits = FALSE)
  if (as.numeric(Sys.time()) - hit$at > ttl) {
    rm(list = key, envir = store)
    return(NULL)
  }
  hit$value
}

#' Store choices for a contract.
#' @noRd
.sashiny_store_choices <- function(engine, contract, value) {
  store <- .sashiny_choices_store(engine)
  if (!is.null(store) && .sashiny_choices_ttl(contract) > 0) {
    assign(.sashiny_contract_sha256(contract), list(value = value, at = as.numeric(Sys.time())),
      envir = store)
  }
  invisible(value)
}

#' Clear an engine's choices cache (the SAS session was replaced).
#' @noRd
.sashiny_clear_choices <- function(engine) {
  if (is.environment(engine)) engine$choices_cache <- NULL
  invisible(NULL)
}

#' Choices for a contract: the cache when fresh, otherwise a load (cached).
#' @noRd
.sashiny_choices <- function(engine, contract) {
  hit <- .sashiny_cached_choices(engine, contract)
  if (!is.null(hit)) {
    return(hit)
  }
  .sashiny_store_choices(engine, contract, sas_engine_choices(engine, contract))
}

#' Load choices without blocking the event loop; resolves to choices or an error.
#'
#' A saspy engine reads them in its worker; a pool reads them on a free
#' session's engine; other engines (the test mock) read them in-process.
#' @noRd
.sashiny_choices_async <- function(engine, contract) {
  hit <- .sashiny_cached_choices(engine, contract)
  if (!is.null(hit)) {
    return(promises::promise_resolve(hit))
  }
  store <- function(value) {
    if (inherits(value, "error")) value else .sashiny_store_choices(engine, contract, value)
  }
  if (inherits(engine, "sashiny_engine_saspy") &&
    (is.null(engine$session_factory) || isTRUE(engine$use_worker))) {
    return(promises::then(.sashiny_worker_choices_promise(engine, contract), store))
  }
  if (inherits(engine, "sashiny_pool")) {
    s <- .sashiny_try_acquire(engine)
    if (!is.null(s) && inherits(s$engine, "sashiny_engine_saspy") &&
      (is.null(s$engine$session_factory) || isTRUE(s$engine$use_worker))) {
      p <- .sashiny_worker_choices_promise(s$engine, contract)
      return(promises::then(p, function(value) {
        .sashiny_release(engine, s, discard = inherits(value, "error"))
        store(value)
      }))
    }
    if (!is.null(s)) .sashiny_release(engine, s)
  }
  promises::promise_resolve(store(tryCatch(sas_engine_choices(engine, contract),
    error = function(e) e)))
}
