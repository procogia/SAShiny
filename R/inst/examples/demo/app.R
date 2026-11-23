# SAShiny demo app (R).
#
# Five tabs (General / Pharma / AML / Forecasting / Survival) run the example contracts on
# a live SAS system chosen with SASHINY_PROFILE: oda (SAS OnDemand for
# Academics, the default), viya or sas94. There is no offline mode: SAShiny runs programs only on a SAS
# system you are licensed to use. Acknowledge this before starting the app with
# options(SAShiny.license_ack = TRUE) or SASHINY_LICENSE_ACK=true.
#
# Connection details come from environment variables; credentials come only
# from ~/.authinfo or SASHINY_SAS_USER / SASHINY_SAS_PASSWORD (see
# docs/live-sas-run-sheet.md):
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

# Allow uploads up to the largest contract `max_size_mb` (the AML example uses
# 200 MB). Shiny's default 5 MiB `maxRequestSize` would otherwise reject files
# the contract explicitly permits; the contract's own `max_size_mb` check is
# still enforced at run time (spec section 7).
options(shiny.maxRequestSize = 250 * 1024^2)

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

tracks <- list(
  general = list("General", file.path(examples_dir, "general", "cars_explorer.sashiny.yml")),
  pharma = list("Pharma", file.path(examples_dir, "pharma", "ae_summary.sashiny.yml")),
  aml = list("AML", file.path(examples_dir, "aml", "cash_aggregation_tuning.sashiny.yml")),
  forecasting = list(
    "Forecasting",
    file.path(examples_dir, "forecasting", "arima_forecast.sashiny.yml")
  ),
  survival = list(
    "Survival",
    file.path(examples_dir, "survival", "survival_analysis.sashiny.yml")
  )
)
contracts <- lapply(tracks, function(t) sas_contract(t[[2]]))

# Chart render callbacks per track (spec 8.5): the forest plot needs CI bars and
# a log axis, which the declarative chart spec does not draw.
# If the callback file cannot be loaded, warn and fall back to the contract's
# declarative chart instead of stopping the app.
survival_render <- tryCatch(
  {
    source(file.path(examples_dir, "survival", "survival_charts.R"), local = TRUE)
    list(forest_plot = forest_chart)
  },
  error = function(e) {
    warning("survival forest-plot callback not loaded (", conditionMessage(e),
            "); using the declarative chart", call. = FALSE)
    NULL
  }
)
chart_render <- list(survival = survival_render)

profiles <- c(
  "SAS ODA (OnDemand for Academics)" = "oda",
  "SAS Viya" = "viya",
  "SAS 9.4" = "sas94"
)

`%||%` <- function(x, y) if (is.null(x)) y else x

env_or_null <- function(name) {
  value <- Sys.getenv(name, unset = "")
  if (nzchar(value)) value else NULL
}

# A pooled live engine for a profile, built from environment variables.
live_engine <- function(profile) {
  factory <- switch(profile,
    oda = function() sas_connect(sas_oda(env_or_null("SASHINY_ODA_REGION") %||% "us1")),
    viya = function() {
      sas_connect(sas_viya(env_or_null("SASHINY_VIYA_URL"),
        context = env_or_null("SASHINY_VIYA_CONTEXT")
      ))
    },
    sas94 = function() sas_connect(sas_94_iom(env_or_null("SASHINY_SAS94_HOST")))
  )
  sas_pool(factory, max_size = 2L)
}

profile <- env_or_null("SASHINY_PROFILE") %||% "oda"
if (!profile %in% profiles) {
  stop("SASHINY_PROFILE must be one of ", paste(profiles, collapse = ", "), call. = FALSE)
}

# One shared live pool per profile, so `max_size` bounds live SAS sessions
# across every browser session rather than per session (issue #62).
shared_live <- new.env(parent = emptyenv())
shared_live_engine <- function(profile) {
  if (is.null(shared_live[[profile]])) {
    shared_live[[profile]] <- live_engine(profile)
  }
  shared_live[[profile]]
}

tabs <- lapply(names(tracks), function(tid) {
  bslib::nav_panel(tracks[[tid]][[1]], sas_program_ui(tid, contracts[[tid]]))
})

ui <- do.call(bslib::page_navbar, c(list(
  title = "SAShiny demo",
  sidebar = bslib::sidebar(
    open = "closed",
    markdown(paste0(
      "Connected to **", names(profiles)[profiles == profile], "** (set `SASHINY_PROFILE`). ",
      "You are responsible for obtaining access to a compatible SAS compiler ",
      "for your chosen profile, and for its licence; SAShiny does not provide SAS. ",
      "Runs need saspy, Java (IOM) and credentials in `~/.authinfo`."
    ))
  ),
  bslib::nav_panel("About", markdown(paste(
    "SAShiny turns unchanged SAS programs into Shiny apps. Each tab is one SAS",
    "program plus a sidecar YAML contract. Choose a connection, set the inputs",
    "and press Run."
  )))
), tabs))

server <- function(input, output, session) {
  engine <- shared_live_engine(profile)
  for (tid in names(tracks)) {
    sas_program_server(tid, contracts[[tid]], engine, render = chart_render[[tid]])
  }
  # Live pools are shared across sessions (issue #62), so they are not closed
  # here; they live for the app's lifetime.
}

shinyApp(ui, server)
