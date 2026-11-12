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
  items <- spec$choices %||% list()
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
    stop("unknown input type ", spec$type, call. = FALSE)
  )
  shiny::tagList(control, if (!is.null(spec$help)) shiny::helpText(spec$help))
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

#' Status text for a result.
#' @noRd
.sashiny_status_text <- function(result) {
  meta <- result$metadata
  lines <- c(paste("status:", result$status), paste("run_id:", result$run_id))
  if (nzchar(meta$sas_version %||% "")) lines <- c(lines, paste("SAS:", meta$sas_version))
  if (identical(meta$recording, "missing")) {
    lines <- c(lines, "offline: no recording matches these inputs")
  } else if (identical(meta$recording, "replayed")) {
    lines <- c(lines, paste("offline: replayed recording from", meta$recorded_at %||% ""))
  }
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

#' Render one output value (or its collection error).
#' @noRd
.sashiny_output_tag <- function(kind, value, spec = NULL, render = NULL) {
  if (is.list(value) && !is.null(value$error) && length(value) == 1L) {
    message <- paste("Could not collect this output:", value$error)
    return(shiny::tags$div(class = "text-danger", message))
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
    stop("the chart produced no image", call. = FALSE)
  }
  openssl::base64_encode(readBin(tmp, "raw", n = file.info(tmp)$size))
}

#' A card (bslib when installed, otherwise a panel).
#' @noRd
.sashiny_card <- function(title, ...) {
  if (requireNamespace("bslib", quietly = TRUE)) {
    bslib::card(bslib::card_header(title), ...)
  } else {
    shiny::wellPanel(shiny::tags$h4(title), ...)
  }
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
    shiny::actionButton(ns("run"), settings$run_label %||% "Run", class = "btn-primary")
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
      shiny::downloadButton(ns(paste0("dl_", oid)), paste("Download", label))
    } else {
      shiny::uiOutput(ns(paste0("out_", oid)))
    }
    .sashiny_card(label, if (!is.null(spec$help)) shiny::helpText(spec$help), body)
  })
  if (identical(settings$layout, "top")) {
    return(shiny::tagList(shiny::wellPanel(controls), status, outputs))
  }
  if (requireNamespace("bslib", quietly = TRUE)) {
    layout <- bslib::layout_sidebar(sidebar = bslib::sidebar(controls), status, outputs)
    return(shiny::tagList(layout))
  }
  layout <- shiny::sidebarLayout(shiny::sidebarPanel(controls), shiny::mainPanel(status, outputs))
  shiny::tagList(layout)
}

#' The server for a SAS program module
#'
#' @param id The module id.
#' @param contract A `sashiny_contract` object.
#' @param engine An engine: [sas_engine_mock()], [sas_connect()] or
#'   [sas_pool()].
#' @param server_override An optional function `function(id, contract, engine)`
#'   that returns a custom server, replacing the auto-generated server.
#' @param render An optional named list of chart render callbacks, keyed by
#'   output id. Each is `function(value, spec, ...)` returning a plot object
#'   (spec section 8.5). Takes precedence over a declarative `spec`.
#' @return A list of reactives: `result`, `status`, `log`.
#' @export
sas_program_server <- function(id, contract, engine, server_override = NULL, render = NULL) {
  if (!is.null(server_override)) {
    return(server_override(id, contract, engine))
  }
  .sashiny_need("shiny", "to run the module server")
  shiny::moduleServer(id, function(input, output, session) {
    inputs <- contract$data$inputs %||% list()
    settings <- contract$data$ui %||% list()
    choice_error <- shiny::reactiveVal("")

    if (any(vapply(inputs, function(s) !is.null(s$choices_from), logical(1)))) {
      found <- tryCatch(sas_engine_choices(engine, contract), error = function(e) e)
      if (inherits(found, "error")) {
        choice_error(paste("could not read choices:", conditionMessage(found)))
      } else {
        .sashiny_update_choices(session, inputs, found)
      }
    }

    result <- shiny::eventReactive(input$run,
      {
        converted <- .sashiny_shiny_values(contract, function(iid) input[[iid]])
        sas_engine_run(engine, contract, converted$values, uploads = converted$uploads)
      },
      ignoreNULL = !isTRUE(settings$auto_run)
    )

    output$status <- shiny::renderText({
      text <- .sashiny_status_text(result())
      if (nzchar(choice_error())) paste(text, choice_error(), sep = "\n") else text
    })
    output$log <- shiny::renderText({
      log <- result()$log
      if (nzchar(log %||% "")) log else "(no log)"
    })

    for (oid in names(contract$data$outputs)) {
          .sashiny_register_output(output, oid, contract$data$outputs[[oid]], result, render[[oid]])
    }

    list(
      result = result,
      status = shiny::reactive(result()$status),
      log = shiny::reactive(result()$log)
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

#' Register the renderer for one output id.
#' @noRd
.sashiny_register_output <- function(output, oid, spec, result, render = NULL) {
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
    return(invisible(NULL))
  }
  output[[paste0("out_", oid)]] <- shiny::renderUI({
    outputs <- result()$outputs
    if (!(oid %in% names(outputs))) {
      return(shiny::tags$small("No output for this run."))
    }
    .sashiny_output_tag(kind, outputs[[oid]], spec, render)
  })
  invisible(NULL)
}
