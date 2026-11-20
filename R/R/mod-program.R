# Shiny modules for SAShiny (issue #8).
#
# `sas_program_ui()` / `sas_program_server()` generate a UI from a contract,
# convert Shiny input values to the contract's JSON form (spec section 2.1), run
# the program on an engine and render one card per contract output (section
# 8.1 values). Either half can be replaced with a custom function.

.sashiny_sample_suffix <- "__sample"
.sashiny_log_colours <- c(
  error = "#b42318", warning = "#b54708", note = "#175cd3", text = "inherit"
)

# ---------------------------------------------------------------- helpers

#' Static choices as a named vector (`names` are labels); empty for `choices_from`.
#' @noRd
.sashiny_ui_choices <- function(spec) {
  # Exact indexing: `spec$choices` would partially match `choices_from` and
  # expose its dataset/column configuration as selectable values.
  items <- spec[["choices"]] %||% list()
  if (length(items) == 0L) {
    return(character(0))
  }
  values <- vapply(items, function(c) if (is.list(c)) c$value else c, character(1))
  labels <- vapply(items, function(c) if (is.list(c)) c$label %||% c$value else c, character(1))
  stats::setNames(values, labels)
}

#' Resolve a contract date (`"today"` or ISO) to a `Date`, or NULL.
#' @noRd
.sashiny_ui_date <- function(value, today) {
  if (is.null(value)) {
    return(NULL)
  }
  if (identical(value, "today")) today else as.Date(value)
}

#' Inputs in `ui$order` first, then the rest in contract order.
#' @noRd
.sashiny_ordered_inputs <- function(contract) {
  inputs <- contract$data$inputs %||% list()
  order <- intersect(unlist(contract$data$ui$order %||% list()), names(inputs))
  c(order, setdiff(names(inputs), order))
}

#' Generate the UI for one contract input, with contract defaults
#'
#' @param iid Input id.
#' @param spec The input specification.
#' @param ns A Shiny namespace function.
#' @param today A `Date` used to resolve `"today"`.
#' @return A Shiny UI element.
#' @noRd
.sashiny_input_ui <- function(iid, spec, ns, today = Sys.Date()) {
  label <- spec$label %||% iid
  id <- ns(iid)
  control <- switch(spec$type,
    numeric = shiny::numericInput(id, label,
      value = spec$default %||% NA, min = spec$min %||% NA, max = spec$max %||% NA,
      step = spec$step %||% (if (isTRUE(spec$integer)) 1 else NA)
    ),
    text = shiny::textInput(id, label, value = spec$default %||% "",
      placeholder = spec$placeholder
    ),
    choice = if (identical(spec$widget, "radio")) {
      shiny::radioButtons(id, label, choices = .sashiny_ui_choices(spec), selected = spec$default)
    } else {
      shiny::selectInput(id, label, choices = .sashiny_ui_choices(spec), selected = spec$default)
    },
    multichoice = if (identical(spec$widget, "checkbox")) {
      shiny::checkboxGroupInput(id, label,
        choices = .sashiny_ui_choices(spec), selected = unlist(spec$default)
      )
    } else {
      shiny::selectInput(id, label,
        choices = .sashiny_ui_choices(spec), selected = unlist(spec$default), multiple = TRUE
      )
    },
    date = shiny::dateInput(id, label,
      value = .sashiny_ui_date(spec$default, today),
      min = .sashiny_ui_date(spec$min, today), max = .sashiny_ui_date(spec$max, today)
    ),
    daterange = shiny::dateRangeInput(id, label,
      start = .sashiny_ui_date((spec$default %||% list())[1][[1]], today),
      end = .sashiny_ui_date((spec$default %||% list())[2][[1]], today),
      min = .sashiny_ui_date(spec$min, today), max = .sashiny_ui_date(spec$max, today)
    ),
    dataset = {
      accept <- paste0(".", unlist(spec$accept %||% .sashiny_default_accept))
      shiny::tagList(
        shiny::fileInput(id, label, accept = accept),
        if (!is.null(spec$sample)) {
          shiny::checkboxInput(ns(paste0(iid, .sashiny_sample_suffix)), "Use the sample file", TRUE)
        }
      )
    },
    .sashiny_abort("values", "unknown input type ", spec$type)
  )
  # The wrapper id lets the server hide controls driven by `values` (spec 6.10).
  shiny::div(
    id = ns(paste0("in__", iid)),
    control, if (!is.null(spec$help)) shiny::helpText(spec$help)
  )
}

#' Convert Shiny input values to the contract's JSON form (section 2.1)
#'
#' @param contract A `sashiny_contract` object.
#' @param read A function returning the Shiny value of an input id.
#' @return `list(values, uploads)`.
#' @noRd
.sashiny_shiny_values <- function(contract, read) {
  inputs <- contract$data$inputs %||% list()
  values <- list()
  uploads <- list()
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    raw <- read(iid)
    if (identical(spec$type, "dataset")) {
      if (is.data.frame(raw) && nrow(raw) > 0L) {
        uploads[[iid]] <- .sashiny_upload_file(raw$datapath[[1]], raw$name[[1]])
      } else if (!is.null(spec$sample) && isTRUE(read(paste0(iid, .sashiny_sample_suffix)))) {
        uploads[[iid]] <- TRUE
      }
      next
    }
    value <- switch(spec$type,
      multichoice = as.list(as.character(raw %||% character(0))),
      date = if (length(raw) == 1L && !is.na(raw)) format(as.Date(raw), "%Y-%m-%d"),
      daterange = if (length(raw) == 2L && !anyNA(raw)) {
        as.list(format(as.Date(raw), "%Y-%m-%d"))
      },
      choice = if (length(raw) == 1L && nzchar(raw)) raw,
      numeric = if (length(raw) == 1L && !is.na(raw)) raw,
      raw
    )
    if (!is.null(value)) values[[iid]] <- value
  }
  list(values = values, uploads = uploads)
}

#' Merge external values over UI values (spec section 6.10)
#'
#' Supplied ids replace the UI value; a supplied `NULL` makes the input
#' absent; dataset ids are ignored. Atomic vectors for `multichoice` and
#' `daterange` inputs become lists, and `Date` values become ISO strings, so
#' callers can pass ordinary R vectors.
#'
#' @param contract A `sashiny_contract` object.
#' @param converted The result of `.sashiny_shiny_values()`.
#' @param external A named list of values, or `NULL`.
#' @return `converted` with merged `values`.
#' @noRd
.sashiny_merge_values <- function(contract, converted, external) {
  if (is.null(external)) {
    return(converted)
  }
  if (!is.list(external) || (length(external) > 0L && is.null(names(external)))) {
    .sashiny_abort("values", "`values()` must return a named list of input values.")
  }
  inputs <- contract$data$inputs %||% list()
  for (iid in names(external)) {
    type <- inputs[[iid]]$type
    if (identical(type, "dataset")) next
    value <- external[[iid]]
    if (is.null(value)) {
      converted$values[[iid]] <- NULL
      next
    }
    if (inherits(value, "Date")) value <- format(value, "%Y-%m-%d")
    if (isTRUE(type %in% c("multichoice", "daterange")) && is.atomic(value)) {
      value <- as.list(value)
    }
    converted$values[iid] <- list(value)
  }
  converted
}

#' CSS that hides the controls of externally supplied inputs (spec section 6.10)
#'
#' @param ids Input ids to hide.
#' @param ns A Shiny namespace function.
#' @return A `<style>` tag, or `NULL` when there is nothing to hide.
#' @noRd
.sashiny_hide_inputs_tag <- function(ids, ns) {
  if (length(ids) == 0L) {
    return(NULL)
  }
  shiny::tags$style(paste0("#", ns(paste0("in__", ids)), " { display: none; }", collapse = "\n"))
}

#' Whether 'bslib' task buttons are available (bslib 0.7.0 or later).
#' @noRd
.sashiny_has_task_button <- function() {
  requireNamespace("bslib", quietly = TRUE) &&
    utils::packageVersion("bslib") >= "0.7.0"
}

#' The Run button.
#'
#' A 'bslib' task button when available: it shows a busy state and is disabled
#' from the click until the run finishes, so a run cannot be started twice.
#' Otherwise a plain action button.
#' @noRd
.sashiny_run_button <- function(id, label) {
  if (.sashiny_has_task_button()) {
    return(bslib::input_task_button(id, label, label_busy = "Running...", type = "primary"))
  }
  shiny::actionButton(id, label, class = "btn-primary")
}

#' Status text for a result.
#' @noRd
.sashiny_status_text <- function(result) {
  meta <- result$metadata
  lines <- c(paste("status:", result$status), paste("run_id:", result$run_id))
  if (nzchar(meta$sas_version %||% "")) lines <- c(lines, paste("SAS:", meta$sas_version))
  for (issue in meta$issues %||% list()) {
    lines <- c(lines, trimws(paste(
      "invalid input", issue$code, issue$input %||% "", issue$message %||% ""
    )))
  }
  if (!is.null(meta$notice)) lines <- c(lines, meta$notice)
  if (!is.null(meta$engine_error)) lines <- c(lines, paste("engine error:", meta$engine_error))
  for (e in meta$collect_errors %||% list()) lines <- c(lines, paste("collect error:", e))
  paste(lines, collapse = "\n")
}

#' Render a section 8.1 table value as an HTML table.
#' @noRd
.sashiny_table_tag <- function(value) {
  tags <- shiny::tags
  numeric <- vapply(value$columns, function(c) {
    identical(c$type, "numeric") && !isTRUE(value$formatted)
  }, logical(1))
  head <- tags$tr(lapply(value$columns, function(c) {
    tags$th(if (nzchar(c$label %||% "")) c$label else c$name, title = c$name)
  }))
  body <- lapply(value$rows, function(row) {
    tags$tr(lapply(seq_along(row), function(j) {
      cell <- row[[j]]
      text <- if (is.null(cell)) {
        ""
      } else if (is.numeric(cell)) {
        .sashiny_format_number(cell)
      } else {
        cell
      }
      tags$td(text, class = if (numeric[[j]]) "text-end")
    }))
  })
  shiny::tagList(
    tags$div(
      style = "max-height: 480px; overflow: auto;",
      tags$table(class = "table table-sm table-striped", tags$thead(head), tags$tbody(body))
    ),
    if (isTRUE(value$truncated)) {
      tags$small(sprintf("Showing %d of %d rows.", length(value$rows), value$total_rows))
    }
  )
}

#' Render a section 8.1 plot value as images.
#' @noRd
.sashiny_plot_tag <- function(value) {
  if (length(value) == 0L) {
    return(shiny::tags$small("No graphs were produced."))
  }
  shiny::tagList(lapply(value, function(p) {
    shiny::tags$img(src = sprintf("data:%s;base64,%s", p$mime, p$data), style = "max-width: 100%;")
  }))
}

#' Render the ODS HTML document in a sandboxed frame (no scripts).
#' @noRd
.sashiny_html_tag <- function(value) {
  if (is.null(value) || !nzchar(value)) {
    return(shiny::tags$small("No HTML output."))
  }
  shiny::tags$iframe(
    srcdoc = value, sandbox = "", title = "SAS output",
    style = "width: 100%; height: 600px; border: 0;"
  )
}

#' Render a section 8.1 log value with lines coloured by level.
#' @noRd
.sashiny_log_tag <- function(value) {
  shiny::tags$pre(
    style = "max-height: 480px; overflow: auto;",
    lapply(value, function(line) {
      colour <- .sashiny_log_colours[[line$level %||% "text"]]
      shiny::tags$span(paste0(line$text, "\n"), style = paste0("color: ", colour, ";"))
    })
  )
}

#' Whether an output value is a collection error (`list(error = ...)`).
#' @noRd
.sashiny_is_collect_error <- function(value) {
  is.list(value) && !is.null(value$error) && length(value) == 1L
}

#' Render a collection error.
#' @noRd
.sashiny_error_tag <- function(value) {
  message <- paste("Could not collect this output:", value$error)
  shiny::tags$div(class = "text-danger", message)
}

#' Render one output value (or its collection error).
#' @noRd
.sashiny_output_tag <- function(kind, value, spec = NULL, render = NULL) {
  if (.sashiny_is_collect_error(value)) {
    return(.sashiny_error_tag(value))
  }
  switch(kind,
    table = .sashiny_table_tag(value),
    plot = .sashiny_plot_tag(value),
    chart = .sashiny_chart_tag(value, spec, render),
    html = .sashiny_html_tag(value),
    log = .sashiny_log_tag(value)
  )
}

#' Render a section 8.1 chart value with the client-side graphics engine.
#'
#' Follows the `shiny::renderPlot` pattern: a render callback (or a declarative
#' spec) produces a plot object. `plotly` widgets are returned as interactive
#' widgets (`renderUI` serves their HTML dependencies); other plots are
#' serialised to a base64 PNG.
#' @noRd
.sashiny_chart_tag <- function(value, spec, render = NULL) {
  if (is.null(value) || length(value$rows %||% list()) == 0L) {
    return(shiny::tags$small("No data for this chart."))
  }
  chart_spec <- spec$spec %||% NULL
  backend <- chart_spec$backend %||% "ggplot2"
  out <- tryCatch(
    {
      plot <- sas_render_chart(value, chart_spec, backend = backend, render = render)
      if (inherits(plot, "plotly")) plot else .sashiny_plot_png(plot)
    },
    error = function(e) e
  )
  if (inherits(out, "error")) {
    reason <- conditionMessage(out)
    message("SAShiny: could not render chart: ", reason)
    return(shiny::tags$small(paste0("Could not render this chart: ", reason)))
  }
  if (inherits(out, "plotly")) {
    return(shiny::tagList(out))
  }
  shiny::tags$img(src = sprintf("data:image/png;base64,%s", out), style = "max-width: 100%;")
}

#' Serialize a plot object to a base64 PNG.
#'
#' Mirrors `shiny::plotPNG`, choosing the method from the plot object so that
#' render callbacks may return either: recorded base plots are replayed, and
#' anything else (`ggplot` objects) is printed. Charts are drawn at 8 x 6
#' inches and 150 dpi (1200 x 900 pixels), the same as the Python module, so
#' they stay sharp when a card scales them to its width.
#' @noRd
.sashiny_plot_png <- function(plot) {
  tmp <- tempfile(fileext = ".png")
  on.exit(unlink(tmp), add = TRUE)
  grDevices::png(tmp, width = 1200, height = 900, res = 150)
  device <- grDevices::dev.cur()
  tryCatch(
    if (inherits(plot, "recordedplot")) grDevices::replayPlot(plot) else print(plot),
    finally = grDevices::dev.off(device)
  )
  if (!file.exists(tmp) || file.info(tmp)$size == 0) {
    .sashiny_abort("values", "the chart produced no image")
  }
  openssl::base64_encode(readBin(tmp, "raw", n = file.info(tmp)$size))
}

#' The client-side view toggle script and styles (spec section 8.6)
#' @noRd
.sashiny_toggle_dependency <- function() {
  .sashiny_need("htmltools", "to build the module UI")
  htmltools::htmlDependency(
    name = "sashiny-toggle",
    version = as.character(utils::packageVersion("SAShiny")),
    src = system.file("www", package = "SAShiny"),
    script = "sashiny-toggle.js",
    stylesheet = "sashiny-toggle.css"
  )
}

.sashiny_view_labels <- c(sas = "SAS graph", sashiny = "SAShiny chart")
.sashiny_group_labels <- c(sas = "SAS graphs", sashiny = "SAShiny charts")

#' A pair of `aria-pressed` buttons that switch views in the browser
#' @noRd
.sashiny_toggle_buttons <- function(labels, view, ...) {
  buttons <- lapply(c("sashiny", "sas"), function(v) {
    on <- identical(v, view)
    shiny::tags$button(
      labels[[v]],
      type = "button", class = if (on) "active",
      `aria-pressed` = if (on) "true" else "false",
      `data-sashiny-set` = v
    )
  })
  shiny::tags$div(class = "sashiny-toggle", role = "group", ..., buttons)
}

#' Render a paired output: the SAS graph and the SAShiny chart (spec section 8.6)
#'
#' Both views are rendered once; the browser switches between them. With
#' `toggle = FALSE` only the default `view` is rendered.
#' @param value The section 8.1 paired value `list(sas, sashiny)`.
#' @param spec The output's contract spec.
#' @param output_id The output id (keys the remembered view).
#' @param group The module's toggle group id.
#' @param view The default view, `"sashiny"` or `"sas"`.
#' @param toggle Whether to show the per-card toggle.
#' @param render An optional chart render callback.
#' @noRd
.sashiny_paired_tag <- function(value, spec, output_id, group, view = "sashiny", toggle = TRUE,
                                render = NULL) {
  chart_spec <- .sashiny_paired_chart_spec(spec)
  pane <- function(part) {
    part_value <- value[[part]]
    if (is.null(part_value)) {
      return(shiny::tags$small("No output for this run."))
    }
    if (.sashiny_is_collect_error(part_value)) {
      return(.sashiny_error_tag(part_value))
    }
    if (identical(part, "sas")) {
      .sashiny_plot_tag(part_value)
    } else {
      .sashiny_chart_tag(part_value, chart_spec, render)
    }
  }
  if (!toggle) {
    return(pane(view))
  }
  panes <- lapply(c("sashiny", "sas"), function(v) {
    shiny::tags$div(
      `data-sashiny-pane` = v,
      hidden = if (!identical(v, view)) NA,
      pane(v)
    )
  })
  shiny::tags$div(
    class = "sashiny-paired",
    `data-sashiny-paired` = "", `data-sashiny-group` = group,
    `data-sashiny-output` = output_id, `data-sashiny-default` = view,
    `data-sashiny-view` = view,
    .sashiny_toggle_dependency(),
    .sashiny_toggle_buttons(.sashiny_view_labels, view,
      `data-sashiny-card-toggle` = "", `aria-label` = "Chart view"
    ),
    panes
  )
}

#' Render the module-wide SAS / SAShiny view toggle (spec section 8.6)
#' @param group The module's toggle group id.
#' @param view The default view of every paired card, or `NULL` when they differ.
#' @noRd
.sashiny_view_toggle_tag <- function(group, view = NULL) {
  shiny::tags$div(
    class = "sashiny-group-toggle",
    `data-sashiny-group-toggle` = "", `data-sashiny-group` = group,
    `data-sashiny-default` = view,
    .sashiny_toggle_dependency(),
    shiny::tags$span("Show:", class = "small"),
    .sashiny_toggle_buttons(.sashiny_group_labels, view,
      `aria-label` = "Chart view for all outputs"
    )
  )
}

#' The default view of each paired output, validating `chart_view` (spec section 8.6)
#' @param contract A `sashiny_contract` object.
#' @param chart_view `"sashiny"`, `"sas"`, or a named list/vector of output id to view.
#' @return A named character vector (empty when the contract has no paired outputs).
#' @noRd
.sashiny_chart_views <- function(contract, chart_view) {
  outputs <- contract$data$outputs %||% list()
  paired <- names(outputs)[vapply(outputs, .sashiny_is_paired, logical(1))]
  views <- c("sashiny", "sas")
  if (is.character(chart_view) && length(chart_view) == 1L && is.null(names(chart_view))) {
    if (!(chart_view %in% views)) {
      .sashiny_abort("values", "chart_view must be 'sashiny' or 'sas', not '", chart_view, "'")
    }
    return(stats::setNames(rep(chart_view, length(paired)), paired))
  }
  if (!(is.list(chart_view) || is.character(chart_view)) || is.null(names(chart_view))) {
    .sashiny_abort("values", "chart_view must be 'sashiny', 'sas' or a named list of output id to view")
  }
  given <- vapply(chart_view, function(v) as.character(v)[[1L]], character(1))
  unknown <- setdiff(names(given), paired)
  if (length(unknown) > 0L) {
    .sashiny_abort("values", "chart_view names outputs that are not paired: ", paste(unknown, collapse = ", "))
  }
  bad <- names(given)[!(given %in% views)]
  if (length(bad) > 0L) {
    .sashiny_abort("values", "chart_view must map outputs to 'sashiny' or 'sas': ", paste(bad, collapse = ", "))
  }
  out <- stats::setNames(rep("sashiny", length(paired)), paired)
  out[names(given)] <- given
  out
}

#' The part of an app-wide `chart_view` that applies to one module
#' @param contract A `sashiny_contract` object.
#' @param chart_view As for [sas_app()].
#' @return A `chart_view` for [sas_program_server()], validated against `contract`.
#' @noRd
.sashiny_module_views <- function(contract, chart_view) {
  if (is.list(chart_view) && !is.null(names(chart_view))) {
    outputs <- contract$data$outputs %||% list()
    paired <- names(outputs)[vapply(outputs, .sashiny_is_paired, logical(1))]
    chart_view <- chart_view[names(chart_view) %in% paired]
    if (length(chart_view) == 0L) {
      chart_view <- "sashiny"
    }
  }
  .sashiny_chart_views(contract, chart_view)
  chart_view
}

#' A card (bslib when installed, otherwise a panel).
#' @noRd
.sashiny_card <- function(title, ...) {
  if (requireNamespace("bslib", quietly = TRUE)) {
    bslib::card(bslib::card_header(title), ..., fill = FALSE)
  } else {
    shiny::wellPanel(shiny::tags$h4(title), ...)
  }
}

# CRAN: the previous `shiny.maxRequestSize` option is saved so it can be
# restored when the module session ends (restore options you change). Stored
# in an environment (not a locked binding) so it can be reassigned at runtime.
#' The upload cap in bytes for a set of contracts: the largest declared
#' `max_size_mb` of their dataset inputs (default 50), or `NULL` with none.
#'
#' Shiny's default `shiny.maxRequestSize` is 5 MiB, which would reject valid
#' datasets up to the contract's (larger) limit with an HTTP 413 before the
#' module ever sees them (issue #54). Per-input limits are still enforced by
#' `read_upload` (V014).
#' @noRd
.sashiny_upload_limit <- function(contracts) {
  limits <- unlist(lapply(contracts, function(contract) {
    vapply(contract$data$inputs %||% list(), function(s) {
      if (identical(s$type, "dataset")) as.numeric(s$max_size_mb %||% 50) else NA_real_
    }, numeric(1))
  }))
  limits <- limits[!is.na(limits)]
  if (length(limits) == 0L) NULL else max(limits) * 1024 * 1024
}

# ---------------------------------------------------------------- module

#' Generate the UI for a SAS program module
#'
#' One control per contract input (with the contract's defaults), a Run
#' button, a Run card with the status and full log, and one card per output.
#'
#' @param id The module id.
#' @param contract A `sashiny_contract` object.
#' @param ui_override An optional function `function(id, contract)` that returns
#'   a custom UI, replacing the auto-generated UI.
#' @param today A `Date` used to resolve `"today"` defaults.
#' @return A Shiny UI definition.
#' @export
sas_program_ui <- function(id, contract, ui_override = NULL, today = Sys.Date()) {
  if (!is.null(ui_override)) {
    return(ui_override(id, contract))
  }
  .sashiny_need("shiny", "to build the module UI")
  ns <- shiny::NS(id)
  inputs <- contract$data$inputs %||% list()
  settings <- contract$data$ui %||% list()
  controls <- shiny::tagList(
    lapply(.sashiny_ordered_inputs(contract), function(iid) {
      .sashiny_input_ui(iid, inputs[[iid]], ns, today)
    }),
    shiny::uiOutput(ns("hide__inputs")),
    .sashiny_run_button(ns("run"), settings$run_label %||% "Run")
  )
  status <- .sashiny_card(
    "Run",
    shiny::verbatimTextOutput(ns("status")),
    shiny::tags$details(
      shiny::tags$summary("Full SAS log"),
      shiny::verbatimTextOutput(ns("log"))
    )
  )
  outputs <- lapply(names(contract$data$outputs), function(oid) {
    spec <- contract$data$outputs[[oid]]
    label <- spec$label %||% oid
    body <- if (identical(spec$type, "download")) {
        # The download button is rendered conditionally (only once a result with
        # this output exists), so a disabled placeholder is shown before the first
        # run and after a failed run (issue #51).
        shiny::uiOutput(ns(paste0("dl_btn_", oid)))
    } else {
      shiny::uiOutput(ns(paste0("out_", oid)))
    }
    .sashiny_card(label, if (!is.null(spec$help)) shiny::helpText(spec$help), body)
  })
  if (any(vapply(contract$data$outputs, .sashiny_is_paired, logical(1)))) {
    # Module-wide SAS / SAShiny toggle (spec section 8.6); empty when the
    # server turns it off.
    outputs <- c(list(shiny::uiOutput(ns("out__view"))), outputs)
  }
  if (identical(settings$layout, "top")) {
    return(shiny::tagList(shiny::wellPanel(controls), status, outputs))
  }
  if (requireNamespace("bslib", quietly = TRUE)) {
      layout <- bslib::layout_sidebar(
        sidebar = bslib::sidebar(controls), status, outputs,
        fillable = FALSE
      )
      return(shiny::tagList(layout))
    }
  layout <- shiny::sidebarLayout(shiny::sidebarPanel(controls), shiny::mainPanel(status, outputs))
  shiny::tagList(layout)
}

#' The server for a SAS program module
#'
#' @param id The module id.
#' @param contract A `sashiny_contract` object.
#' @param engine An engine: [sas_connect()], [sas_engine_saspy()] or
#'   [sas_pool()].
#' @param server_override An optional function `function(id, contract, engine)`
#'   that returns a custom server, replacing the auto-generated server.
#' @param render An optional named list of chart render callbacks, keyed by
#'   output id. Each is `function(value, spec, ...)` returning a plot object
#'   (spec section 8.5). Takes precedence over a declarative `spec`.
#' @param chart_view The default view of paired outputs (spec section 8.6):
#'   `"sashiny"` (the default) for the 'SAShiny' chart, `"sas"` for the
#'   original 'SAS' graph, or a named list of paired output id to view.
#' @param chart_toggle Whether to show the 'SAS' / 'SAShiny' toggles (default
#'   `TRUE`). With `FALSE` each paired card shows only its default view.
#' @param values An optional reactive returning a named list of input values
#'   in the contract's JSON form (spec section 6.10). Supplied ids replace the
#'   UI value (validated exactly like UI values); other ids come from the UI.
#'   With `ui.auto_run: true`, a change of `values()` starts a run after
#'   `debounce_ms`.
#' @param hide_inputs Whether to hide the controls of the ids supplied by
#'   `values()` (default `FALSE`).
#' @param debounce_ms Debounce interval in milliseconds for auto-runs driven by
#'   `values()` (default `500`).
#' @details In a running app, runs do not block other browser sessions: each
#'   [sas_connect()] engine and each [sas_pool()] session keeps its 'SAS'
#'   session in a persistent worker process (spec section 6.5). Ending the
#'   browser session cancels its in-flight run.
#'
#'   This function never changes global options. In your own app, set
#'   `options(shiny.maxRequestSize = )` to at least the largest `max_size_mb`
#'   of your contracts' dataset inputs (Shiny's default is 5 MiB);
#'   [sas_app()] does this for you. Each input's own `max_size_mb` is still
#'   enforced on every upload (V014).
#' @return A list of reactives: `result`, `status`, `log`.
#' @export
sas_program_server <- function(id, contract, engine, server_override = NULL, render = NULL,
                               chart_view = "sashiny", chart_toggle = TRUE, values = NULL,
                               hide_inputs = FALSE, debounce_ms = 500) {
  .sashiny_check_engine(engine)
  if (!is.null(values) && !is.function(values)) {
    .sashiny_abort("values", "`values` must be a reactive (or function) returning a named list.")
  }
  if (!is.numeric(debounce_ms) || length(debounce_ms) != 1L || is.na(debounce_ms) ||
    debounce_ms < 0) {
    .sashiny_abort("values", "`debounce_ms` must be a single non-negative number.")
  }
  views <- .sashiny_chart_views(contract, chart_view)
  if (!is.null(server_override)) {
    return(server_override(id, contract, engine))
  }
  .sashiny_need("shiny", "to run the module server")
  shiny::moduleServer(id, function(input, output, session) {
    inputs <- contract$data$inputs %||% list()
    settings <- contract$data$ui %||% list()
    choice_error <- shiny::reactiveVal("")

    # choices_from (spec section 6.4): load once per app and contract (cached
    # with a time-to-live), in the background in a running app, so a new
    # browser session never waits for SAS.
    if (.sashiny_has_choices_from(contract)) {
      apply_choices <- function(found) {
        if (inherits(found, "error")) {
          choice_error(paste("could not read choices:", conditionMessage(found)))
        } else {
          choice_error("")
          .sashiny_update_choices(session, inputs, found)
        }
      }
      cached <- .sashiny_cached_choices(engine, contract)
      if (!is.null(cached)) {
        apply_choices(cached)
      } else if (shiny::isRunning() && requireNamespace("promises", quietly = TRUE) &&
        requireNamespace("later", quietly = TRUE)) {
        .sashiny_choices_loading(session, inputs)
        promises::then(.sashiny_choices_async(engine, contract), apply_choices)
      } else {
        apply_choices(tryCatch(.sashiny_choices(engine, contract), error = function(e) e))
      }
    }

    # A reactiveVal starts as NULL, so the status card can render the choice
    # error before the first run without forcing an uninitialised eventReactive
    # (which raises a shiny.silent.error under ignoreNULL=TRUE).
    result <- shiny::reactiveVal(NULL)
    # Run the engine off the event loop (issue #44; spec section 6.5): saspy
    # engines and pools run in persistent worker processes polled by `later`,
    # so the main process keeps serving other sessions. testServer cannot
    # await a background process, so it runs synchronously.
    use_extended <- shiny::isRunning() && requireNamespace("callr", quietly = TRUE) &&
      requireNamespace("later", quietly = TRUE) && requireNamespace("promises", quietly = TRUE)
    # Whether a run is in flight; only an ExtendedTask can be running between
    # flushes (the synchronous path finishes inside the click handler).
    running <- function() FALSE
    # UI values with any external `values()` merged over them (spec 6.10).
    current_values <- function() {
      converted <- .sashiny_shiny_values(contract, function(iid) input[[iid]])
      .sashiny_merge_values(contract, converted, if (!is.null(values)) values())
    }
    # Set when `values()` changes during a run: one more run follows it.
    pending <- FALSE
    if (use_extended) {
      run_task <- shiny::ExtendedTask$new(function(contract, values, uploads) {
        run_id <- .sashiny_run_id()
        promises::catch(
          .sashiny_run_async(engine, contract, values, uploads, run_id = run_id, session = session),
          function(e) .sashiny_engine_error(run_id, list(), e)
        )
      })
      running <- function() identical(run_task$status(), "running")
      # Keep the task button busy and disabled until the run finishes.
      if (.sashiny_has_task_button()) bslib::bind_task_button(run_task, "run")
      start_run <- function() {
        converted <- current_values()
        run_task$invoke(contract, converted$values, converted$uploads)
      }
      shiny::observeEvent(input$run,
        {
          # Ignore a click while a run is in flight, so a burst of clicks does
          # not queue one SAS run per click (ExtendedTask queues invocations).
          if (running()) {
            return(invisible(NULL))
          }
          start_run()
        },
        ignoreNULL = !isTRUE(settings$auto_run)
      )
      shiny::observeEvent(run_task$result(), {
        result(run_task$result())
        if (pending) {
          pending <<- FALSE
          start_run()
        }
      })
    } else {
      start_run <- function() {
        converted <- current_values()
        run_contract <- contract
        if (.sashiny_has_choices_from(contract)) {
          run_contract$cached_choices <- .sashiny_cached_choices(engine, contract)
        }
        result(sas_engine_run(engine, run_contract, converted$values, uploads = converted$uploads))
      }
      shiny::observeEvent(input$run, start_run(), ignoreNULL = !isTRUE(settings$auto_run))
    }

    if (!is.null(values)) {
      if (isTRUE(settings$auto_run)) {
        # Debounced auto-run on external changes; the first value is used by
        # the auto_run run at session start, so it does not run again.
        settled <- shiny::debounce(values, debounce_ms)
        shiny::observeEvent(settled(),
          {
            if (running()) pending <<- TRUE else start_run()
          },
          ignoreInit = TRUE, ignoreNULL = FALSE
        )
      }
      output$hide__inputs <- shiny::renderUI({
        if (isTRUE(hide_inputs)) {
          supplied <- intersect(names(values() %||% list()), names(inputs))
          .sashiny_hide_inputs_tag(supplied, session$ns)
        }
      })
    }

    output$status <- shiny::renderText({
      if (running()) {
        return("running...")
      }
      res <- result()
      if (is.null(res)) {
        # Before the first run, surface a choices_from load failure so the
        # user is not left with empty dropdowns and no explanation (#68).
        return(if (nzchar(choice_error())) choice_error() else "")
      }
      text <- .sashiny_status_text(res)
      if (nzchar(choice_error())) paste(text, choice_error(), sep = "\n") else text
    })
    output$log <- shiny::renderText({
      res <- result()
      log <- if (is.null(res)) "" else res$log
      if (nzchar(log %||% "")) log else "(no log)"
    })

    group <- session$ns("views")
    for (oid in names(contract$data$outputs)) {
      pairing <- if (oid %in% names(views)) {
        list(group = group, view = views[[oid]], toggle = isTRUE(chart_toggle))
      }
      .sashiny_register_output(
        output, oid, contract$data$outputs[[oid]], result, render[[oid]], pairing,
        ns = session$ns
      )
    }
    if (length(views) > 0L) {
      defaults <- unique(unname(views))
      group_view <- if (length(defaults) == 1L) defaults
      output$out__view <- shiny::renderUI({
        if (isTRUE(chart_toggle)) .sashiny_view_toggle_tag(group, group_view)
      })
    }

    list(
      result = result,
      status = shiny::reactive({
        res <- result()
        if (is.null(res)) "idle" else res$status
      }),
      log = shiny::reactive({
        res <- result()
        if (is.null(res)) "" else res$log
      })
    )
  })
}

#' Fill `choices_from` inputs (spec section 6.4).
#' @noRd
.sashiny_update_choices <- function(session, inputs, found) {
  for (iid in names(found)) {
    spec <- inputs[[iid]]
    choices <- stats::setNames(
      vapply(found[[iid]], function(c) c$value, character(1)),
      vapply(found[[iid]], function(c) c$label %||% c$value, character(1))
    )
    if (identical(spec$type, "choice") && identical(spec$widget, "radio")) {
      shiny::updateRadioButtons(session, iid, choices = choices, selected = spec$default)
    } else if (identical(spec$type, "multichoice") && identical(spec$widget, "checkbox")) {
      shiny::updateCheckboxGroupInput(session, iid,
        choices = choices, selected = unlist(spec$default)
      )
    } else {
      shiny::updateSelectInput(session, iid, choices = choices, selected = unlist(spec$default))
    }
  }
}

#' Show "Loading choices..." in each `choices_from` input until they load.
#' @noRd
.sashiny_choices_loading <- function(session, inputs) {
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    if (is.null(spec$choices_from)) next
    placeholder <- c("Loading choices\u2026" = "")
    if (identical(spec$type, "choice") && identical(spec$widget, "radio")) {
      shiny::updateRadioButtons(session, iid, choices = placeholder)
    } else if (identical(spec$type, "multichoice") && identical(spec$widget, "checkbox")) {
      shiny::updateCheckboxGroupInput(session, iid, choices = placeholder)
    } else {
      shiny::updateSelectInput(session, iid, choices = placeholder)
    }
  }
}

#' Register the renderer for one output id.
#' @noRd
.sashiny_register_output <- function(output, oid, spec, result, render = NULL, pairing = NULL,
                                     ns = shiny::NS(NULL)) {
  # The caller passes render[[oid]] and pairing from a loop; force them now, or
  # the lazy promises would be evaluated inside renderUI with the loop's last oid.
  force(render)
  force(pairing)
  kind <- spec$type
  if (identical(kind, "download")) {
    value <- function() {
      v <- result()$outputs[[oid]]
      shiny::req(is.list(v), !is.null(v$data))
      v
    }
    output[[paste0("dl_", oid)]] <- shiny::downloadHandler(
      filename = function() value()$filename,
      content = function(file) writeBin(openssl::base64_decode(value()$data), file),
      contentType = NULL
    )
    # Render the download button only once a result with this output exists, so
    # a disabled placeholder is shown before the first run and after a failed
    # run (issue #51). The real button keeps the handler's id `dl_<oid>`,
    # namespaced because renderUI does not add the module prefix. The
    # placeholder has no id, so it does not reuse the output's id.
    label <- spec$label %||% oid
    output[[paste0("dl_btn_", oid)]] <- shiny::renderUI({
      v <- result()$outputs[[oid]]
      if (is.list(v) && !is.null(v$data)) {
        shiny::downloadButton(ns(paste0("dl_", oid)), paste("Download", label))
      } else {
        shiny::tags$button(
          type = "button", class = "btn btn-default", disabled = NA,
          paste("Download", label)
        )
      }
    })
    return(invisible(NULL))
  }
  output[[paste0("out_", oid)]] <- shiny::renderUI({
    outputs <- result()$outputs
    if (!(oid %in% names(outputs))) {
      return(shiny::tags$small("No output for this run."))
    }
    value <- outputs[[oid]]
    if (!is.null(pairing)) {
      if (.sashiny_is_collect_error(value)) {
        return(.sashiny_error_tag(value))
      }
      return(.sashiny_paired_tag(value, spec, oid, pairing$group,
        view = pairing$view, toggle = pairing$toggle, render = render
      ))
    }
    .sashiny_output_tag(kind, value, spec, render)
  })
  invisible(NULL)
}
