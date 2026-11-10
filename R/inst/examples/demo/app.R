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
library(SAShiny)

# Locate the repository's examples/ directory by walking up from the app
# directory (R/inst/examples/demo -> repo root is four levels up), so the app
# works from a source checkout regardless of the working directory depth.
find_examples_dir <- function(start = getwd(), max_up = 6L) {
  dir <- normalizePath(start, mustWork = FALSE)
  for (i in seq_len(max_up)) {
    candidate <- file.path(dir, "examples", "general", "cars_explorer.sashiny.yml")
    if (file.exists(candidate)) {
      return(file.path(dir, "examples"))
    }
    parent <- dirname(dir)
    if (identical(parent, dir)) break
    dir <- parent
  }
  stop(
    "Could not find the SAShiny examples/ directory. Run the demo from a ",
    "source checkout, e.g. shiny::runApp(\"R/inst/examples/demo\") from the ",
    "repository root.",
    call. = FALSE
  )
}
examples_dir <- find_examples_dir()

tracks <- list(
  General = file.path(examples_dir, "general", "cars_explorer.sashiny.yml"),
  Pharma = file.path(examples_dir, "pharma", "ae_summary.sashiny.yml"),
  AML = file.path(examples_dir, "aml", "cash_aggregation_tuning.sashiny.yml")
)

contracts <- lapply(tracks, sas_contract)

profiles <- c("Offline", "ODA", "ProCogia Viya", "ProCogia 9.4")

ui <- bslib::page_navbar(
  title = "SAShiny demo",
  sidebar = bslib::sidebar(
    selectInput("profile", "Connection profile", profiles, selected = "Offline"),
    checkboxInput("live", "Live SAS", value = FALSE),
    markdown("Live SAS requires the saspy engine (issue #6).")
  ),
  bslib::nav_panel("About", markdown(
    paste(
      "SAShiny demo: unchanged SAS programs as the server of a Shiny app.",
      "Select a track, choose a connection profile, set inputs, and press Run."
    )
  )),
  bslib::nav_panel("General", sas_program_ui("general", contracts$General)),
  bslib::nav_panel("Pharma", sas_program_ui("pharma", contracts$Pharma)),
  bslib::nav_panel("AML", sas_program_ui("aml", contracts$AML))
)

server <- function(input, output, session) {
  # Offline mode uses the mock engine; live SAS is stubbed until #6.
  engine <- sas_engine_mock()
  sas_program_server("general", contracts$General, engine)
  sas_program_server("pharma", contracts$Pharma, engine)
  sas_program_server("aml", contracts$AML, engine)
}

shinyApp(ui, server)