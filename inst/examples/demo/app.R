# SAShiny Lisbon demo app (R).
#
# Three tabs (General / Pharma / AML) run the example contracts. The sidebar
# picks the SAS connection:
#
# - Offline replays recordings from examples/recordings (spec section 8.3).
# - ODA, ProCogia Viya and ProCogia SAS 9.4 run live through saspy. Every live
#   run is also saved as a recording, so running the demo inputs once live
#   fills the offline fallback. If a live session cannot start, the run falls
#   back to the matching recording and says so in the Run card.
#
# Connection details come from environment variables; credentials come only
# from ~/.authinfo (see docs/live-sas-run-sheet.md):
#
#   SASHINY_ODA_REGION    us1 | us2 | eu1 | ap1 | ap2   (default us1)
#   SASHINY_VIYA_URL      https://viya.example.com
#   SASHINY_VIYA_CONTEXT  SAS Studio compute context     (optional)
#   SASHINY_SAS94_HOST    sas94.example.com
#
# Run from the repository root:
#
#   Rscript -e 'shiny::runApp("R/inst/examples/demo")'

library(shiny)
library(SAShiny)

# Locate the repository's examples/ directory by walking up from the app
# directory, so the app works from a source checkout at any depth.
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
recordings_dir <- file.path(examples_dir, "recordings")

tracks <- list(
  general = list("General", file.path(examples_dir, "general", "cars_explorer.sashiny.yml")),
  pharma = list("Pharma", file.path(examples_dir, "pharma", "ae_summary.sashiny.yml")),
  aml = list("AML", file.path(examples_dir, "aml", "cash_aggregation_tuning.sashiny.yml"))
)
contracts <- lapply(tracks, function(t) sas_contract(t[[2]]))

profiles <- c(
  "Offline (recordings)" = "offline",
  "SAS OnDemand for Academics" = "oda",
  "ProCogia SAS Viya (VPN)" = "viya",
  "ProCogia SAS 9.4 (VPN)" = "sas94"
)

`%||%` <- function(x, y) if (is.null(x)) y else x

env_or_null <- function(name) {
  value <- Sys.getenv(name, unset = "")
  if (nzchar(value)) value else NULL
}

# A pooled live engine for a profile, built from environment variables.
live_engine <- function(profile) {
  factory <- switch(profile,
    oda = function() {
      region <- env_or_null("SASHINY_ODA_REGION") %||% "us1"
      sas_connect("oda", region = region, record_to = recordings_dir)
    },
    viya = function() {
      sas_connect("viya",
        url = env_or_null("SASHINY_VIYA_URL"),
        context = env_or_null("SASHINY_VIYA_CONTEXT"),
        record_to = recordings_dir
      )
    },
    sas94 = function() {
      sas_connect("sas94", host = env_or_null("SASHINY_SAS94_HOST"), record_to = recordings_dir)
    }
  )
  sas_pool(factory, max_size = 2L)
}

# An engine that routes each run to the selected profile and falls back to
# the offline recordings when live SAS is unavailable.
demo_engine <- function(profile) {
  offline <- sas_engine_mock(recordings_dir)
  live <- new.env(parent = emptyenv())
  current <- function() {
    name <- shiny::isolate(profile())
    if (identical(name, "offline")) {
      return(list(name = name, engine = offline))
    }
    if (is.null(live[[name]])) live[[name]] <- live_engine(name)
    list(name = name, engine = live[[name]])
  }
  structure(list(current = current, offline = offline, live = live), class = "demo_engine")
}

run_demo <- function(engine, contract, values, today = Sys.Date(),
                     uploads = NULL, run_id = NULL) {
  selected <- engine$current()
  run <- function(e) {
    sas_engine_run(e, contract, values, today = today, uploads = uploads, run_id = run_id)
  }
  if (identical(selected$name, "offline")) {
    return(run(selected$engine))
  }
  result <- tryCatch(run(selected$engine), error = function(e) e)
  reason <- if (inherits(result, "error")) {
    conditionMessage(result)
  } else {
    result$metadata$engine_error
  }
  if (is.null(reason)) {
    return(result)
  }
  fallback <- run(engine$offline)
  label <- names(profiles)[profiles == selected$name]
  fallback$metadata$notice <- sprintf(
    "live %s unavailable (%s); showing the offline recording", label, reason
  )
  fallback
}
registerS3method("sas_engine_run", "demo_engine", run_demo)

choices_demo <- function(engine, contract) {
  sas_engine_choices(engine$current()$engine, contract)
}
registerS3method("sas_engine_choices", "demo_engine", choices_demo)

tabs <- lapply(names(tracks), function(tid) {
  bslib::nav_panel(tracks[[tid]][[1]], sas_program_ui(tid, contracts[[tid]]))
})

ui <- do.call(bslib::page_navbar, c(list(
  title = "SAShiny demo",
  sidebar = bslib::sidebar(
    open = "closed",
    selectInput("profile", "SAS connection", profiles, selected = "offline"),
    markdown(paste(
      "Offline replays recorded runs. Live profiles need saspy, Java (IOM) and",
      "credentials in `~/.authinfo`."
    ))
  ),
  bslib::nav_panel("About", markdown(paste(
    "SAShiny turns unchanged SAS programs into Shiny apps. Each tab is one SAS",
    "program plus a sidecar YAML contract. Choose a connection, set the inputs",
    "and press Run."
  )))
), tabs))

server <- function(input, output, session) {
  profile <- reactive(input$profile %||% "offline")
  engine <- demo_engine(profile)
  for (tid in names(tracks)) {
    sas_program_server(tid, contracts[[tid]], engine)
  }
  session$onSessionEnded(function() {
    for (name in ls(engine$live)) sas_engine_close(engine$live[[name]])
  })
}

shinyApp(ui, server)
