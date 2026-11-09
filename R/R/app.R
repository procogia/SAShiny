# App helpers for SAShiny.
#
# `sas_app()` builds a multi-program Shiny app from a list of contracts, using
# the Shiny modules and an engine. It is the one-liner entry point for hosting
# several SAS programs as tabs in a single app.

#' Build a multi-program Shiny app from a list of contracts
#'
#' @param contracts A list of `sashiny_contract` objects or paths to
#'   `*.sashiny.yml` files (loaded automatically).
#' @param engine An engine object (e.g. from [sas_engine_mock()]).
#' @param title The app title.
#' @return A Shiny app object (from [shiny::shinyApp()]).
#' @export
sas_app <- function(contracts, engine, title = "SAShiny") {
  rlang::check_installed("shiny", reason = "to build a Shiny app")
  loaded <- lapply(contracts, function(c) {
    if (inherits(c, "sashiny_contract")) c else sas_contract(c)
  })

  module_id <- function(i, contract) {
    contract$data$id %||% paste0("program_", i)
  }

  ui <- shiny::navbarPage(
    title,
    !!!lapply(seq_along(loaded), function(i) {
      contract <- loaded[[i]]
      shiny::tabPanel(
        contract$data$title %||% paste0("Program ", i),
        sas_program_ui(module_id(i, contract), contract)
      )
    })
  )

  server <- function(input, output, session) {
    for (i in seq_along(loaded)) {
      sas_program_server(module_id(i, loaded[[i]]), loaded[[i]], engine)
    }
  }

  shiny::shinyApp(ui, server)
}