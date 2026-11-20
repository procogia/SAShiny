# Data frame accessors for run results (spec section 8.7, non-normative).
#
# The section 8.1 values stay the cross-language wire format; these helpers
# turn them into data frames for analysis in R.

#' Get a table output as a data frame
#'
#' Converts a `table` or `chart` output (spec section 8.1) to a data frame:
#' one row per table row, one column per 'SAS' column. Numeric columns are
#' doubles (missing values are `NA`); formatted and character columns are
#' character. Each column keeps its 'SAS' label and format in the `label` and
#' `format.sas` attributes, as 'haven' does. The frame has `total_rows` and
#' `truncated` attributes.
#'
#' @param result A `sashiny_result` from [sas_run()] or [sas_engine_run()].
#' @param id The output id from the contract.
#' @param tibble `TRUE` to return a tibble (needs the 'tibble' package).
#' @return A data frame.
#' @examples
#' result <- structure(list(outputs = list(stats = list(
#'   columns = list(list(name = "n", type = "numeric", label = "Count", format = "")),
#'   rows = list(list(1), list(2)), total_rows = 2L, truncated = FALSE, formatted = FALSE
#' ))), class = "sashiny_result")
#' sas_result_table(result, "stats")
#' @export
sas_result_table <- function(result, id, tibble = FALSE) {
  value <- .sashiny_result_output(result, id)
  if (!.sashiny_is_table_value(value)) {
    stop(sprintf("output '%s' is not a table or chart", id), call. = FALSE)
  }
  df <- .sashiny_table_df(value)
  for (j in seq_along(value$columns)) {
    col <- value$columns[[j]]
    attr(df[[j]], "label") <- col$label %||% ""
    attr(df[[j]], "format.sas") <- col$format %||% ""
  }
  attr(df, "total_rows") <- value$total_rows
  attr(df, "truncated") <- isTRUE(value$truncated)
  if (isTRUE(tibble)) {
    rlang::check_installed("tibble", "to return a tibble")
    keep <- attributes(df)[c("total_rows", "truncated")]
    df <- tibble::as_tibble(df)
    attributes(df)[names(keep)] <- keep
  }
  df
}

#' Get the log of a run as a data frame
#'
#' One row per line of the full log of the run, split as in spec section 8.2.
#' `type` is `"ERROR"`, `"WARNING"` or `"NOTE"` for lines starting with that
#' word (the same rule as the run status, spec section 6.5), otherwise
#' `"other"`.
#'
#' @param result A `sashiny_result`.
#' @return A data frame with columns `line` (integer), `type` and `text`.
#' @examples
#' result <- structure(list(log = "NOTE: ok\nERROR: bad\n"), class = "sashiny_result")
#' sas_result_log(result)
#' @export
sas_result_log <- function(result) {
  lines <- .sashiny_split_log(result$log %||% "")
  .sashiny_log_frame(lines, vapply(lines, .sashiny_log_type, character(1), USE.NAMES = FALSE))
}

#' Get every output in its most useful form
#'
#' `table` and `chart` outputs become data frames ([sas_result_table()]), `log`
#' outputs become log data frames, and every other output keeps its spec
#' section 8.1 value. An output that could not be collected keeps its
#' `list(error = )` value.
#'
#' @param result A `sashiny_result`.
#' @return A named list, one element per output.
#' @examples
#' result <- structure(list(outputs = list(page = "<html></html>")), class = "sashiny_result")
#' names(sas_result_outputs(result))
#' @export
sas_result_outputs <- function(result) {
  outputs <- result$outputs %||% list()
  stats::setNames(lapply(names(outputs), function(id) {
    value <- outputs[[id]]
    if (.sashiny_is_table_value(value)) {
      return(sas_result_table(result, id))
    }
    if (.sashiny_is_log_value(value)) {
      levels <- vapply(value, function(l) l$level, character(1))
      types <- c(error = "ERROR", warning = "WARNING", note = "NOTE", text = "other")[levels]
      return(.sashiny_log_frame(vapply(value, function(l) l$text, character(1)), unname(types)))
    }
    value
  }), names(outputs))
}

#' The output value for `id`, or an error naming the id (spec section 8.7).
#' @noRd
.sashiny_result_output <- function(result, id) {
  outputs <- result$outputs %||% list()
  if (!is.character(id) || length(id) != 1L || !id %in% names(outputs)) {
    stop(sprintf("no output '%s' in this result", paste(id, collapse = ",")), call. = FALSE)
  }
  value <- outputs[[id]]
  if (is.list(value) && !is.null(names(value)) && identical(names(value), "error")) {
    stop(sprintf("output '%s' could not be collected: %s", id, value$error), call. = FALSE)
  }
  value
}

#' Whether a value has the section 8.1 table shape.
#' @noRd
.sashiny_is_table_value <- function(value) {
  is.list(value) && !is.null(value$columns) && !is.null(value$rows)
}

#' Whether a value is a section 8.1 log value.
#' @noRd
.sashiny_is_log_value <- function(value) {
  is.list(value) && is.null(names(value)) && length(value) > 0L &&
    all(vapply(value, function(l) is.list(l) && !is.null(l$level) && !is.null(l$text), logical(1)))
}

#' The section 8.7 log type of one line (same rule as spec section 6.5).
#' @noRd
.sashiny_log_type <- function(line) {
  c(error = "ERROR", warning = "WARNING", note = "NOTE", text = "other")[[.sashiny_log_level(line)]]
}

#' A log data frame from lines and their types.
#' @noRd
.sashiny_log_frame <- function(text, type) {
  data.frame(
    line = seq_along(text), type = as.character(type), text = as.character(text),
    stringsAsFactors = FALSE
  )
}
