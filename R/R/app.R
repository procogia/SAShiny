# App helpers for SAShiny.
#
# `sas_app()` builds a multi-program Shiny app from a list of contracts, using
# the Shiny modules and an engine. It is the one-liner entry point for hosting
# several SAS programs as tabs in a single app.

#' Build a multi-program Shiny app from a list of contracts
#'
#' @param contracts A list of `sashiny_contract` objects or paths to
#'   `*.sashiny.yml` files (loaded automatically).
#' @param engine An engine from [sas_connect()], [sas_engine_saspy()] or
#'   [sas_pool()].
#' @param title The app title.
#' @param publish `TRUE` to add a "Publish" tab that deploys the app to Posit
#'   Connect with [sas_publish()]. Off by default, and never shown when the
#'   app itself runs on Posit Connect.
#' @param chart_view The default view of paired outputs (spec section 8.6),
#'   passed to every module: `"sashiny"` (the default), `"sas"`, or a named
#'   list of paired output id to view. Each module uses the entries for its
#'   own outputs.
#' @param chart_toggle Whether to show the 'SAS' / 'SAShiny' toggles (default
#'   `TRUE`).
#' @return A Shiny app object (from [shiny::shinyApp()]).
#' @examples
#' \dontrun{
#' # Needs a licensed 'SAS' system and saspy; not run during checks.
#' path <- system.file("examples", "minimal", "minimal.sashiny.yml", package = "SAShiny")
#' engine <- sas_pool(function() sas_connect("oda", license_ack = TRUE), max_size = 2L)
#' shiny::runApp(sas_app(list(path), engine, publish = TRUE))
#' }
#' @export
sas_app <- function(contracts, engine, title = "SAShiny", publish = FALSE,
                    chart_view = "sashiny", chart_toggle = TRUE) {
  .sashiny_need("shiny", "to build a Shiny app")
  .sashiny_check_engine(engine)
  show_publish <- isTRUE(publish) && !.sashiny_on_connect()
  loaded <- lapply(contracts, function(c) {
    if (inherits(c, "sashiny_contract")) c else sas_contract(c)
  })

  module_id <- function(contract) {
    contract$data$id %||% .sashiny_default_module_id(contract$data$program)
  }

  ids <- vapply(loaded, module_id, character(1))
  # Reject duplicate module ids (spec section 2): two tabs sharing a namespace
  # would collide on every input and output id.
  if (anyDuplicated(ids)) {
    dup <- ids[duplicated(ids)][[1]]
    stop(sprintf("duplicate module id %s: two contracts resolve to the same id", dup),
         call. = FALSE)
  }
  module_views <- lapply(loaded, function(contract) {
    .sashiny_module_views(contract, chart_view)
  })
  if (is.list(chart_view) && !is.null(names(chart_view))) {
    used <- unlist(lapply(module_views, names))
    unknown <- setdiff(names(chart_view), used)
    if (length(unknown) > 0L) {
      stop("chart_view names outputs that are not paired: ", paste(unknown, collapse = ", "),
           call. = FALSE)
    }
  }

  tabs <- lapply(seq_along(loaded), function(i) {
    contract <- loaded[[i]]
    shiny::tabPanel(
      contract$data$title %||% paste0("Program ", i),
      sas_program_ui(ids[[i]], contract)
    )
  })
  if (show_publish) {
    tabs <- c(tabs, list(shiny::tabPanel("Publish", .sashiny_publish_ui("sashiny_publish"))))
  }
  ui <- do.call(shiny::navbarPage, c(list(title), tabs))

  server <- function(input, output, session) {
    for (i in seq_along(loaded)) {
      sas_program_server(ids[[i]], loaded[[i]], engine,
        chart_view = module_views[[i]], chart_toggle = chart_toggle
      )
    }
    if (show_publish) .sashiny_publish_server("sashiny_publish")
  }

  shiny::shinyApp(ui, server)
}
