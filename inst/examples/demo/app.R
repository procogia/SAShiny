# SAShiny Lisbon demo app skeleton (R).
#
# A minimal multi-tab Shiny app that loads the three example contracts
# (general / pharma / aml) and renders a placeholder UI. The "Run" action
# validates the inputs and shows the rendered macro values, standing in for the
# mock engine until the full engine and Shiny modules land (issues #5, #8).
#
# Run from the repository root:
#
#   shiny::runApp("R/inst/examples/demo")

library(shiny)

# Locate the examples directory (repo root is ../../.. from inst/examples/demo).
examples_dir <- normalizePath(file.path("..", "..", "..", "examples"),
                              mustWork = FALSE)
if (!dir.exists(examples_dir)) {
  examples_dir <- system.file("examples", package = "SAShiny")
}

tracks <- list(
  General = file.path(examples_dir, "general", "cars_explorer.sashiny.yml"),
  Pharma = file.path(examples_dir, "pharma", "ae_summary.sashiny.yml"),
  AML = file.path(examples_dir, "aml", "cash_aggregation_tuning.sashiny.yml")
)

contracts <- lapply(tracks, function(p) if (file.exists(p)) sas_contract(p) else NULL)
contracts <- contracts[!vapply(contracts, is.null, logical(1))]

input_ui <- function(iid, spec) {
  kind <- spec$type
  label <- spec$label %||% iid
  switch(kind,
    numeric = numericInput(iid, label, spec$default %||% 0),
    text = textInput(iid, label, spec$default %||% ""),
    choice = textInput(iid, label, spec$default %||% ""),
    multichoice = checkboxGroupInput(
      iid, label,
      choices = vapply(spec$choices %||% list(), function(c) {
        if (is.character(c)) c else c$value
      }, character(1))
    ),
    date = textInput(iid, label, ""),
    daterange = textInput(iid, label, ""),
    dataset = fileInput(iid, label),
    textInput(iid, label, "")
  )
}

track_ui <- function(name, contract) {
  inputs <- contract$data$inputs %||% list()
  controls <- lapply(names(inputs), function(iid) input_ui(iid, inputs[[iid]]))
  tabPanel(
    name,
    h3(contract$data$title %||% name),
    controls,
    actionButton("run", "Run", class = "btn-primary"),
    verbatimTextOutput("result")
  )
}

ui <- navbarPage(
  "SAShiny demo",
  tabPanel("About", markdown(
    "SAShiny demo: unchanged SAS programs as the server of a Shiny app. ",
    "Select a track, set inputs, and press Run."
  )),
  !!!lapply(names(contracts), function(n) track_ui(n, contracts[[n]]))
)

server <- function(input, output, session) {
  output$result <- renderPrint({
    req(input$run)
    # Simplified: render the first track that has any inputs. The full app
    # tracks the active tab explicitly.
    for (name in names(contracts)) {
      contract <- contracts[[name]]
      inputs <- contract$data$inputs %||% list()
      values <- lapply(names(inputs), function(iid) input[[iid]])
      names(values) <- names(inputs)
      if (length(values) > 0L) {
        res <- sas_render_values(contract$data, values)
        if (length(res$issues) > 0L) {
          return(paste(vapply(res$issues, function(i) paste(i$code, i$path, i$message),
                              character(1)), collapse = "\n"))
        }
        return(paste(paste(names(res$macros), unlist(res$macros), sep = " = "),
                     collapse = "\n"))
      }
    }
    "Set inputs and press Run."
  })
}

shinyApp(ui, server)