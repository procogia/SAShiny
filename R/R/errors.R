# Classed errors (#130 H5).
#
# Every error SAShiny raises has the class `sashiny_error`, plus one of
# `sashiny_error_contract`, `_values`, `_engine`, `_license`, `_upload`,
# `_deploy` or `_run`, so callers can catch them by class:
#
#   tryCatch(sas_check(result), sashiny_error_run = function(e) ...)
#
# Engine runs still RETURN error results and never raise (spec section 6.5).

#' Raise a classed SAShiny error with `cli::cli_abort()`.
#'
#' The message parts are pasted together and passed as data, so braces in
#' user values (paths, SAS text) are never interpreted by 'cli'.
#' @param kind One of `contract`, `values`, `engine`, `license`, `upload`,
#'   `deploy`, `run`.
#' @param ... Message parts, pasted with no separator.
#' @param .data Extra fields stored on the condition.
#' @noRd
.sashiny_abort <- function(kind, ..., .data = list()) {
  msg <- paste0(...)
  do.call(cli::cli_abort, c(
    list(
      "{msg}",
      class = c(paste0("sashiny_error_", kind), "sashiny_error"),
      call = NULL,
      .envir = environment()
    ),
    .data
  ))
}

#' Check that a run succeeded
#'
#' Returns `result` invisibly when its status is `"success"` or `"warning"`.
#' Otherwise raises an error of class `sashiny_error_run` that names the run id
#' and the first `ERROR` line of the log (or the engine error, or the first
#' invalid input). Use it to stop a script at a failed run, as
#' `httr2::resp_check_status()` does for HTTP responses.
#'
#' @param result A `sashiny_result` from [sas_run()] or [sas_engine_run()].
#' @return `result`, invisibly.
#' @examples
#' ok <- structure(list(run_id = "r1", status = "success", log = "", metadata = list()),
#'   class = "sashiny_result")
#' sas_check(ok)
#' bad <- structure(list(run_id = "r2", status = "error", log = "ERROR: no data\n",
#'   metadata = list()), class = "sashiny_result")
#' try(sas_check(bad))
#' @export
sas_check <- function(result) {
  if (result$status %in% c("success", "warning")) {
    return(invisible(result))
  }
  reason <- .sashiny_failure_reason(result)
  .sashiny_abort("run", "run ", result$run_id, " failed: ", reason,
    .data = list(result = result)
  )
}

#' The first reason a run failed: ERROR line, engine error or invalid input.
#' @noRd
.sashiny_failure_reason <- function(result) {
  first <- .sashiny_first_error(result$log)
  if (!is.null(first)) {
    return(sprintf("%s (log line %d)", first$text, first$line))
  }
  meta <- result$metadata %||% list()
  if (!is.null(meta$engine_error)) {
    return(meta$engine_error)
  }
  issues <- meta$issues %||% list()
  if (length(issues)) {
    i <- issues[[1]]
    # Skip empty parts (an upload issue has no input id), as Python does (#153).
    parts <- c("invalid input", i$code %||% "", i$input %||% "", i$message %||% "")
    return(paste(parts[nzchar(parts)], collapse = " "))
  }
  "no ERROR line in the log"
}

#' The first ERROR line of a log, with its 1-based line number, or NULL.
#' @noRd
.sashiny_first_error <- function(log) {
  lines <- .sashiny_split_log(log %||% "")
  hit <- which(startsWith(lines, "ERROR"))
  if (length(hit) == 0L) NULL else list(line = hit[[1]], text = lines[[hit[[1]]]])
}

#' @export
format.sashiny_result <- function(x, ...) {
  meta <- x$metadata %||% list()
  status <- x$status %||% ""
  coloured <- switch(status,
    success = cli::col_green(status),
    warning = cli::col_yellow(status),
    error = cli::col_red(status),
    status
  )
  head <- paste0("<sashiny result> ", coloured)
  seconds <- meta$seconds %||% .sashiny_duration(meta$started_at, meta$ended_at)
  lines <- c(
    head,
    paste0("  run id:   ", x$run_id %||% ""),
    if (!is.null(seconds)) sprintf("  duration: %.2f s", as.numeric(seconds)),
    paste0("  backend:  ", meta$backend %||% meta$engine %||% "")
  )
  if (!identical(status, "success") && !identical(status, "warning")) {
    lines <- c(lines, paste0("  reason:   ", .sashiny_failure_reason(x)))
  }
  outputs <- x$outputs %||% list()
  if (length(outputs)) {
    lines <- c(lines, "  outputs:")
    for (id in names(outputs)) lines <- c(lines, paste0("    ", id, ": ", .sashiny_output_summary(outputs[[id]])))
  }
  lines
}

#' @export
print.sashiny_result <- function(x, ...) {
  cat(format(x, ...), sep = "\n")
  invisible(x)
}

#' Run duration in seconds from ISO timestamps, or NULL.
#' @noRd
.sashiny_duration <- function(started, ended) {
  if (is.null(started) || is.null(ended)) {
    return(NULL)
  }
  t <- as.POSIXct(c(started, ended), format = "%Y-%m-%dT%H:%M:%OS", tz = "UTC")
  if (anyNA(t)) NULL else as.numeric(difftime(t[[2]], t[[1]], units = "secs"))
}

#' A one-line summary of an output value (spec section 8.1).
#' @noRd
.sashiny_output_summary <- function(value) {
  if (is.list(value) && identical(names(value), "error")) {
    return(paste("not collected:", value$error))
  }
  if (.sashiny_is_table_value(value)) {
    n <- length(value$rows)
    total <- value$total_rows
    more <- if (!is.null(total) && total > n) sprintf(" of %s", format(total)) else ""
    return(sprintf("table, %d row(s)%s x %d column(s)", n, more, length(value$columns)))
  }
  if (.sashiny_is_log_value(value)) {
    return(sprintf("log, %d line(s)", length(value)))
  }
  if (is.list(value) && !is.null(value$sas) && !is.null(value$sashiny)) {
    return("paired SAS graph and SAShiny chart")
  }
  if (is.list(value) && !is.null(value$filename)) {
    return(paste("download", value$filename))
  }
  if (is.character(value)) {
    return(sprintf("html, %d characters", nchar(value)))
  }
  if (is.list(value)) {
    return(sprintf("plot, %d graph(s)", length(value)))
  }
  class(value)[[1]]
}
