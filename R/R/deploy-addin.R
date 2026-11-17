# RStudio / Positron addin "Deploy SAShiny app..." (spec section 6.8).
#
# CRAN: the addin only generates files (no network). Applying stays an explicit
# second step: the user runs sas_deploy(apply = TRUE) or the generated guide.

#' The deploy panel UI.
#' @noRd
.sashiny_deploy_ui <- function(id) {
  ns <- shiny::NS(id)
  targets <- sas_deploy_targets()
  shiny::tagList(
    shiny::h4("Deploy a SAShiny app"),
    shiny::p(
      "Generates deployment files for one platform. Nothing is uploaded: run",
      "sas_deploy(..., apply = TRUE) or follow the generated guide afterwards.",
      "Credential files are never bundled."
    ),
    shiny::textInput(ns("app_dir"), "App directory", value = getwd()),
    shiny::selectInput(ns("target"), "Target",
      choices = stats::setNames(targets$id, paste0(targets$label, " (", targets$languages, ")"))
    ),
    shiny::radioButtons(ns("method"), "SAS connection",
      choices = c("SAS Viya (http)" = "http", "SAS ODA (iom)" = "oda", "SAS 9.4 (iom)" = "iom")
    ),
    shiny::textInput(ns("detail"), "Viya URL, ODA region or SAS 9.4 host", value = ""),
    shiny::checkboxInput(ns("private"), "The SAS server is reachable only over a private network"),
    shiny::checkboxInput(ns("license_ack"), paste(
      "I confirm that the deployed app runs programs only on a SAS system",
      "I am licensed to use."
    )),
    shiny::actionButton(ns("deploy"), "Generate", class = "btn-primary"),
    shiny::verbatimTextOutput(ns("status"))
  )
}

#' Build a profile list from the panel fields.
#' @noRd
.sashiny_addin_profile <- function(method, detail, private) {
  detail <- trimws(detail %||% "")
  prof <- switch(method,
    http = list(name = "viya", method = "http", url = detail),
    oda = list(name = "oda", method = "iom", oda_region = if (nzchar(detail)) detail else "us1"),
    iom = list(name = "sas94", method = "iom", iomhost = detail)
  )
  if (isTRUE(private)) prof$requires_vpn <- TRUE
  prof
}

#' The deploy panel server.
#' @noRd
.sashiny_deploy_server <- function(id, deploy = sas_deploy) {
  shiny::moduleServer(id, function(input, output, session) {
    status <- shiny::reactiveVal("")
    shiny::observeEvent(input$deploy, {
      out <- tryCatch(
        {
          spec <- .sashiny_lookup_target(input$target)
          args <- list(
            input$app_dir, input$target,
            profile = .sashiny_addin_profile(input$method, input$detail, input$private),
            license_ack = isTRUE(input$license_ack)
          )
          if (isTRUE(input$private)) args[[spec$private_network_option]] <- TRUE
          res <- do.call(deploy, args)
          paste0(
            "Wrote ", length(res$files), " files to ", res$out_dir, ".",
            if (length(res$excluded)) paste0(" Not bundled: ", paste(res$excluded, collapse = ", ")),
            "\nNext: follow the generated guide, or run sas_deploy(..., apply = TRUE)."
          )
        },
        error = function(e) paste("Generate failed:", conditionMessage(e))
      )
      status(out)
    })
    output$status <- shiny::renderText(status())
  })
}

#' RStudio / Positron addin: generate deployment files for a SAShiny app
#'
#' Opens a small Shiny gadget that lists [sas_deploy_targets()], collects the
#' app directory, 'SAS' connection and licence acknowledgement, and calls
#' [sas_deploy()] to generate the files. Nothing is uploaded; applying is an
#' explicit second step. Registered in `inst/rstudio/addins.dcf`.
#'
#' @param app_dir The initial app directory.
#' @return Invisibly, `NULL`. Called for its side effect.
#' @examples
#' \dontrun{
#' # Interactive only: opens a gadget in the IDE viewer.
#' sas_deploy_addin()
#' }
#' @export
sas_deploy_addin <- function(app_dir = getwd()) {
  .sashiny_need("shiny", "to run the deploy addin")
  ui <- shiny::fluidPage(.sashiny_deploy_ui("deploy"))
  server <- function(input, output, session) {
    shiny::updateTextInput(session, "deploy-app_dir", value = app_dir)
    .sashiny_deploy_server("deploy")
  }
  viewer <- if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    shiny::paneViewer()
  } else {
    shiny::browserViewer()
  }
  shiny::runGadget(ui, server, viewer = viewer)
  invisible(NULL)
}
