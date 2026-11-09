# Shiny modules for SAShiny (issue #8).
#
# `sas_program_ui()` / `sas_program_server()` generate a UI from a contract and
# run it through an engine, collecting tables, plots, HTML, log and downloads.
# The auto-generated UI can be overridden with custom modules.

#' Generate a UI for one contract input
#'
#' @param iid Input id.
#' @param spec The input specification.
#' @param ns A Shiny namespace function.
#' @return A Shiny UI element.
#' @noRd
.sashiny_input_ui <- function(iid, spec, ns) {
  kind <- spec$type
  label <- spec$label %||% iid
  id <- ns(iid)
  switch(kind,
    numeric = shiny::numericInput(id, label, spec$default %||% 0),
    text = shiny::textInput(id, label, spec$default %||% ""),
    choice = shiny::selectInput(
      id, label,
      choices = vapply(spec$choices %||% list(), function(c) {
        if (is.character(c)) c else c$value
      }, character(1)),
      selected = spec$default %||% NULL
    ),
    multichoice = shiny::checkboxGroupInput(
      id, label,
      choices = vapply(spec$choices %||% list(), function(c) {
        if (is.character(c)) c else c$value
      }, character(1)),
      selected = spec$default %||% NULL
    ),
    date = shiny::dateInput(id, label, value = spec$default %||% NULL),
    daterange = shiny::dateRangeInput(
      id, label,
      start = (spec$default %||% list())[[1]] %||% NULL,
      end = (spec$default %||% list())[[2]] %||% NULL
    ),
    dataset = shiny::fileInput(id, label),
    shiny::textInput(id, label, "")
  )
}

#' Generate the UI for a SAS program module
#'
#' @param id The module id.
#' @param contract A `sashiny_contract` object.
#' @param ui_override An optional function `function(id, contract)` that returns
#'   a custom UI, replacing the auto-generated UI.
#' @return A Shiny UI definition.
#' @export
sas_program_ui <- function(id, contract, ui_override = NULL) {
  if (!is.null(ui_override)) {
    return(ui_override(id, contract))
  }
  ns <- shiny::NS(id)
  inputs <- contract$data$inputs %||% list()
  controls <- lapply(names(inputs), function(iid) {
    .sashiny_input_ui(iid, inputs[[iid]], ns)
  })
  shiny::tagList(
    controls,
    shiny::actionButton(ns("run"), contract$data$ui$run_label %||% "Run",
                        class = "btn-primary"),
    shiny::hr(),
    shiny::verbatimTextOutput(ns("status")),
    shiny::verbatimTextOutput(ns("log")),
    shiny::tableOutput(ns("table")),
    shiny::uiOutput(ns("plots")),
    shiny::htmlOutput(ns("html")),
    shiny::uiOutput(ns("downloads"))
  )
}

#' The server for a SAS program module
#'
#' @param id The module id.
#' @param contract A `sashiny_contract` object.
#' @param engine An engine object (e.g. from [sas_engine_mock()]).
#' @param server_override An optional function `function(id, contract, engine)`
#'   that returns a custom server, replacing the auto-generated server.
#' @return A list of reactives: `result`, `status`, `log`.
#' @export
sas_program_server <- function(id, contract, engine, server_override = NULL) {
  if (!is.null(server_override)) {
    return(server_override(id, contract, engine))
  }
  shiny::moduleServer(id, function(input, output, session) {
    ns <- session$ns
    inputs <- contract$data$inputs %||% list()

    result <- shiny::eventReactive(input$run, {
      values <- lapply(names(inputs), function(iid) input[[iid]])
      names(values) <- names(inputs)
      sas_engine_run(engine, contract, values)
    })

    output$status <- shiny::renderPrint({
      r <- result()
      cat("status:", r$status, "\n")
      cat("run_id:", r$run_id, "\n")
      if (!is.null(r$metadata$sas_version) && nzchar(r$metadata$sas_version)) {
        cat("SAS:", r$metadata$sas_version, "\n")
      }
    })

    output$log <- shiny::renderPrint({
      r <- result()
      if (nzchar(r$log)) cat(r$log) else cat("(no log)")
    })

    output$table <- shiny::renderTable({
      r <- result()
      tbl <- r$outputs$table
      if (is.null(tbl)) return(NULL)
      as.data.frame(tbl$rows, stringsAsFactors = FALSE)
    })

    output$plots <- shiny::renderUI({
      r <- result()
      plots <- r$outputs$plot
      if (is.null(plots)) return(NULL)
      shiny::tagList(lapply(seq_along(plots), function(i) {
        shiny::imageOutput(ns(paste0("plot_", i)))
      }))
    })

    output$html <- shiny::renderUI({
      r <- result()
      if (is.null(r$outputs$html)) return(NULL)
      shiny::HTML(r$outputs$html)
    })

    output$downloads <- shiny::renderUI({
      r <- result()
      dl <- r$outputs$download
      if (is.null(dl)) return(NULL)
      shiny::tagList(lapply(names(dl), function(n) {
        shiny::downloadButton(ns(paste0("dl_", n)), n)
      }))
    })

    list(result = result, status = shiny::reactive(result()$status),
         log = shiny::reactive(result()$log))
  })
}