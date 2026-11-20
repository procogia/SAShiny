# Expose a SAShiny contract as an 'ellmer' tool (experiment, #130 J7; not shipped).
#
# A contract declares typed inputs with limits, choices and defaults. This file
# maps them to an ellmer tool so a chat model calls a validated SAS program
# instead of writing SAS code. The model only picks input values; SAShiny
# validates them (V001-V014) and SAS does the computation.

.preview_rows <- 20L

#' The tool name: the contract file stem (`x.sashiny.yml` -> `x`).
tool_name <- function(contract) {
  stem <- basename(contract$path %||% contract$data$program)
  stem <- sub("(\\.sashiny)?\\.ya?ml$|\\.sas$", "", stem, ignore.case = TRUE)
  stem <- substr(gsub("[^A-Za-z0-9_-]", "_", stem), 1L, 64L)
  if (nzchar(stem)) stem else "sas_program"
}

`%||%` <- function(x, y) if (is.null(x)) y else x

.choice_values <- function(spec) {
  vapply(spec$choices %||% list(), function(c) if (is.list(c)) c$value else as.character(c), "")
}

.date_hint <- function(label, spec, today) {
  bound <- function(v) if (identical(v, "today")) format(today) else v
  parts <- c(label, "(ISO date YYYY-MM-DD")
  if (!is.null(spec$min)) parts <- c(parts, paste("from", bound(spec$min)))
  if (!is.null(spec$max)) parts <- c(parts, paste("to", bound(spec$max)))
  paste0(paste(parts, collapse = " "), ")")
}

#' An ellmer type for one contract input (NULL for dataset inputs).
.input_type <- function(spec, today) {
  label <- spec$label %||% ""
  required <- !isTRUE(spec$optional) && is.null(spec$default)
  switch(spec$type,
    numeric = {
      bounds <- c(
        if (!is.null(spec$min)) paste("min", spec$min),
        if (!is.null(spec$max)) paste("max", spec$max)
      )
      desc <- trimws(paste(label, if (length(bounds)) paste0("(", paste(bounds, collapse = ", "), ")")))
      if (isTRUE(spec$integer)) {
        ellmer::type_integer(desc, required = required)
      } else {
        ellmer::type_number(desc, required = required)
      }
    },
    text = ellmer::type_string(label, required = required),
    choice = if (!is.null(spec$choices)) {
      ellmer::type_enum(.choice_values(spec), label, required = required)
    } else {
      ellmer::type_string(label, required = required)
    },
    multichoice = ellmer::type_array(
      if (!is.null(spec$choices)) ellmer::type_enum(.choice_values(spec)) else ellmer::type_string(),
      label, required = required
    ),
    date = ellmer::type_string(.date_hint(label, spec, today), required = required),
    daterange = ellmer::type_array(ellmer::type_string(),
      .date_hint(paste(label, "[start, end]"), spec, today), required = required
    ),
    dataset = NULL
  )
}

#' The tool arguments: one ellmer type per non-dataset input.
tool_arguments <- function(contract, today = Sys.Date()) {
  inputs <- contract$data$inputs %||% list()
  types <- lapply(inputs, .input_type, today = today)
  types[!vapply(types, is.null, logical(1))]
}

.with_defaults <- function(contract, args, today) {
  for (iid in names(contract$data$inputs %||% list())) {
    spec <- contract$data$inputs[[iid]]
    if (!is.null(args[[iid]]) || is.null(spec$default) || identical(spec$type, "dataset")) next
    default <- spec$default
    if (spec$type %in% c("date", "daterange")) {
      default <- lapply(default, function(d) if (identical(d, "today")) format(today) else d)
      if (identical(spec$type, "date")) default <- default[[1]]
    }
    args[[iid]] <- default
  }
  args
}

#' The compact summary sent back to the model (no raw HTML).
summarise_result <- function(contract, result) {
  lines <- strsplit(result$log %||% "", "\n", fixed = TRUE)[[1]]
  errors <- grep("^ERROR", lines, value = TRUE)
  tables <- list()
  for (oid in names(contract$data$outputs)) {
    value <- result$outputs[[oid]]
    if (!identical(contract$data$outputs[[oid]]$type, "table") || !is.list(value) ||
      is.null(value$rows)) {
      next
    }
    tables[[oid]] <- list(
      columns = vapply(value$columns, function(c) if (is.list(c)) c$name else c, ""),
      rows = utils::head(value$rows, .preview_rows),
      total_rows = value$total_rows %||% length(value$rows)
    )
  }
  list(
    run_id = result$run_id, status = result$status,
    error = if (length(errors)) trimws(errors[[1]]),
    issues = result$metadata$issues %||% list(),
    tables = tables
  )
}

#' Run the contract with model-supplied `args`; return the JSON summary.
#'
#' Invalid arguments come back to the model as V-code issues, never as errors.
call_tool <- function(contract, engine, args, today = Sys.Date()) {
  args <- lapply(args, function(v) if (is.atomic(v) && length(v) > 1L) as.list(v) else v)
  out <- tryCatch(
    summarise_result(contract, SAShiny::sas_run(contract, engine,
      .with_defaults(contract, args, today), today = today)),
    error = function(e) list(run_id = NULL, status = "error", error = conditionMessage(e),
      issues = list())
  )
  jsonlite::toJSON(out, auto_unbox = TRUE, null = "null")
}

#' An 'ellmer' tool that runs `contract` on `engine`.
sas_as_tool <- function(contract, engine) {
  arguments <- tool_arguments(contract)
  fun <- function(...) call_tool(contract, engine, list(...))
  formals(fun) <- stats::setNames(rep(list(NULL), length(arguments)), names(arguments))
  body(fun) <- quote({
    args <- as.list(environment())
    args <- args[!vapply(args, is.null, logical(1))]
    call_tool(contract, engine, args)
  })
  data <- contract$data
  description <- paste(c(data$title, trimws(data$description %||% ""),
    "Runs a validated SAS program; returns status, the first ERROR and table previews."),
    collapse = " ")
  ellmer::tool(fun, description, name = tool_name(contract), arguments = arguments)
}