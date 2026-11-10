# SAShiny Lisbon demo app (R).
#
# A multi-tab Shiny app (General / Pharma / AML) that runs the three example
# contracts through the mock engine (offline mode). The connection-profile
# picker and live/offline toggle are present; live SAS is stubbed until the
# saspy engine (issue #6) and live SAS reports (issue #11) land.
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

profiles <- c("Offline", "ODA", "ProCogia Viya", "ProCogia 9.4")

ui <- navbarPage(
  "SAShiny demo",
  tabPanel("About", markdown(
      "SAShiny demo: unchanged SAS programs as the server of a Shiny app. Select a track, choose a connection profile, set inputs, and press Run."
    )),
  tabPanel("General", sas_program_ui("general", contracts$General)),
  tabPanel("Pharma", sas_program_ui("pharma", contracts$Pharma)),
  tabPanel("AML", sas_program_ui("aml", contracts$AML)),
  sidebar = sidebarPanel(
    selectInput("profile", "Connection profile", profiles, selected = "Offline"),
    checkboxInput("live", "Live SAS", value = FALSE),
    markdown("Live SAS requires the saspy engine (issue #6).")
  )
)

server <- function(input, output, session) {
  # Offline mode uses the mock engine; live SAS is stubbed until #6.
  engine <- sas_engine_mock()
  sas_program_server("general", contracts$General, engine)
  sas_program_server("pharma", contracts$Pharma, engine)
  sas_program_server("aml", contracts$AML, engine)
}

shinyApp(ui, server)