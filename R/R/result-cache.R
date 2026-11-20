# Opt-in result cache (spec section 6.11; #130 J5).
#
# With `run.cache: true`, a run whose contract, program and rendered inputs
# match an earlier `success` or `warning` run reuses that result for
# `run.cache_ttl_seconds`. The default is off. The cache is per R process and
# shared by every engine and pool; the in-memory store is an LRU of 100
# entries and can be replaced with `.sashiny_cache_set_store()`.

.sashiny_cache_state <- new.env(parent = emptyenv())

#' A new in-memory LRU result store
#'
#' A store is a list of functions `get(key)` (returning
#' `list(result, stored_at)` or `NULL`), `set(key, result, stored_at)`,
#' `delete(key)`, `clear()` and `size()`. An external cache can supply the
#' same functions.
#'
#' @param max_entries The most results kept.
#' @return A store (a list of functions).
#' @noRd
.sashiny_lru_store <- function(max_entries = 100L) {
  if (!is.numeric(max_entries) || length(max_entries) != 1L || max_entries < 1) {
    stop("`max_entries` must be at least 1.", call. = FALSE)
  }
  data <- new.env(parent = emptyenv())
  order <- character(0)
  touch <- function(key) order <<- c(setdiff(order, key), key)
  list(
    get = function(key) {
      if (!exists(key, envir = data, inherits = FALSE)) {
        return(NULL)
      }
      touch(key)
      get(key, envir = data, inherits = FALSE)
    },
    set = function(key, result, stored_at) {
      assign(key, list(result = result, stored_at = stored_at), envir = data)
      touch(key)
      while (length(order) > max_entries) {
        rm(list = order[[1L]], envir = data)
        order <<- order[-1L]
      }
      invisible(NULL)
    },
    delete = function(key) {
      if (exists(key, envir = data, inherits = FALSE)) rm(list = key, envir = data)
      order <<- setdiff(order, key)
      invisible(NULL)
    },
    clear = function() {
      rm(list = ls(data, all.names = TRUE), envir = data)
      order <<- character(0)
      invisible(NULL)
    },
    size = function() length(order)
  )
}

#' The process-wide result store (created on first use).
#' @noRd
.sashiny_cache_store <- function() {
  if (is.null(.sashiny_cache_state$store)) .sashiny_cache_state$store <- .sashiny_lru_store()
  .sashiny_cache_state$store
}

#' Replace the process-wide result store
#'
#' @param store A store from `.sashiny_lru_store()` or an external cache with
#'   the same functions, or `NULL` for a fresh in-memory LRU.
#' @return The previous store, invisibly.
#' @noRd
.sashiny_cache_set_store <- function(store) {
  previous <- .sashiny_cache_state$store
  .sashiny_cache_state$store <- store %||% .sashiny_lru_store()
  invisible(previous)
}

#' Whether a contract opts in with `run.cache: true`.
#' @noRd
.sashiny_cache_enabled <- function(contract) {
  isTRUE((contract$data$run %||% list())$cache)
}

#' The result-cache key text (spec section 6.11).
#'
#' @param contract_sha256,program_sha256 Hex digests (section 8.4).
#' @param macros A named list or character vector of rendered macros.
#' @param uploads A named character vector of upload digests.
#' @noRd
.sashiny_cache_key_text <- function(contract_sha256, program_sha256, macros,
                                    uploads = character(0)) {
  lines <- c(
    "sashiny-cache-key 1", paste0("contract ", contract_sha256),
    paste0("program ", program_sha256)
  )
  if (length(macros) > 0L) {
    lines <- c(lines, paste0("macro ", names(macros), "=", vapply(macros, as.character, "")))
  }
  if (length(uploads) > 0L) {
    lines <- c(lines, paste0("upload ", names(uploads), " ", unname(uploads)))
  }
  paste0(paste(lines, collapse = "\n"), "\n")
}

#' The cache key of a run, or NULL when the run bypasses the cache
#'
#' Invalid values, unreadable uploads and `choices_from` lists that are not
#' loaded yet bypass the cache.
#' @noRd
.sashiny_cache_key <- function(engine, contract, values, today, uploads) {
  found <- contract$cached_choices
  if (is.null(found) && .sashiny_has_choices_from(contract)) {
    found <- .sashiny_cached_choices(engine, contract)
    if (is.null(found)) {
      return(NULL)
    }
  }
  flags <- lapply(uploads %||% list(), function(v) !is.null(v) && !isFALSE(v))
  res <- tryCatch(
    sas_render_values(contract$data, values, today,
      choices_override = .sashiny_choice_override(found %||% list()), uploads = flags
    ),
    error = function(e) NULL
  )
  if (is.null(res) || length(res$issues) > 0L) {
    return(NULL)
  }
  digests <- tryCatch(
    {
      files <- .sashiny_resolve_files(contract, uploads)
      out <- character(0)
      for (iid in names(contract$data$inputs %||% list())) {
        path <- files[[iid]]
        if (is.null(path)) next
        if (inherits(path, "sashiny_upload_file")) path <- path$path
        out[[iid]] <- .sashiny_sha256(.sashiny_read_bytes(path))
      }
      out
    },
    error = function(e) NULL
  )
  if (is.null(digests)) {
    return(NULL)
  }
  text <- .sashiny_cache_key_text(
    .sashiny_contract_sha256(contract), .sashiny_program_sha256(contract), res$macros, digests
  )
  .sashiny_sha256(charToRaw(enc2utf8(text)))
}

#' Look up a run in the cache
#'
#' @return `list(key, hit)`: `key` is `NULL` when the run bypasses the cache;
#'   `hit` is the cached result (with `cache_hit` and `cached_at`) or `NULL`.
#' @noRd
.sashiny_cache_lookup <- function(engine, contract, values, today = Sys.Date(), uploads = NULL) {
  if (!.sashiny_cache_enabled(contract)) {
    return(list(key = NULL, hit = NULL))
  }
  key <- .sashiny_cache_key(engine, contract, values, today, uploads)
  if (is.null(key)) {
    return(list(key = NULL, hit = NULL))
  }
  store <- .sashiny_cache_store()
  entry <- store$get(key)
  if (is.null(entry)) {
    return(list(key = key, hit = NULL))
  }
  ttl <- as.numeric((contract$data$run %||% list())$cache_ttl_seconds %||% 3600)
  if (as.numeric(Sys.time()) - entry$stored_at > ttl) {
    store$delete(key)
    return(list(key = key, hit = NULL))
  }
  hit <- entry$result
  hit$metadata$cache_hit <- TRUE
  hit$metadata$cached_at <- format(
    as.POSIXct(entry$stored_at, origin = "1970-01-01", tz = "UTC"), "%Y-%m-%dT%H:%M:%SZ"
  )
  list(key = key, hit = hit)
}

#' Store a result under `key` when it is cacheable; return the result.
#' @noRd
.sashiny_cache_store_result <- function(key, result) {
  if (!is.null(key) && isTRUE(result$status %in% c("success", "warning"))) {
    .sashiny_cache_store()$set(key, result, as.numeric(Sys.time()))
  }
  result
}

#' Run through the cache: a hit, or `run()` whose result is stored.
#'
#' @param run A function of no arguments returning a result.
#' @noRd
.sashiny_cached_run <- function(engine, contract, values, run, today = Sys.Date(),
                                uploads = NULL) {
  found <- .sashiny_cache_lookup(engine, contract, values, today, uploads)
  if (!is.null(found$hit)) {
    return(found$hit)
  }
  .sashiny_cache_store_result(found$key, run())
}
