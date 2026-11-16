# Publishing SAShiny apps to Posit Connect (spec section 6.7).
#
# `sas_publish()` deploys an app directory with the official 'rsconnect'
# client. It never bundles credential files. 'SAS' credentials and the licence
# acknowledgement reach the deployed app only as Connect environment
# variables, whose values 'rsconnect' sends over an encrypted connection and
# does not store in the bundle.
#
# CRAN: nothing here runs during R CMD check. Every network call is behind
# `sas_publish()` or the addin, and the tests replace the deploy function, so
# no network is used.

#' File names that are never bundled (spec section 6.7).
#' @noRd
.sashiny_secret_names <- c(".authinfo", "_authinfo", ".netrc", "_netrc", ".Renviron", ".env")

#' Whether a bundle-relative path is a credential file.
#' @noRd
.sashiny_is_secret <- function(path) {
  name <- basename(path)
  name %in% .sashiny_secret_names | grepl("\\.(pem|key)$", name, ignore.case = TRUE)
}

#' The files of an app directory to bundle, and the credential files left out.
#'
#' Hidden version-control and 'rsconnect' metadata folders are skipped too.
#' @param app_dir The app directory.
#' @return `list(files, excluded)`, both relative to `app_dir`.
#' @noRd
.sashiny_bundle_files <- function(app_dir) {
  files <- list.files(app_dir, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  files <- files[!grepl("^(\\.git|\\.Rproj\\.user|rsconnect|\\.venv|__pycache__)(/|$)", files)]
  secret <- .sashiny_is_secret(files)
  list(files = files[!secret], excluded = files[secret])
}

#' Whether the current process is running on Posit Connect.
#' @noRd
.sashiny_on_connect <- function() {
  identical(toupper(Sys.getenv("RSTUDIO_PRODUCT")), "CONNECT") ||
    nzchar(Sys.getenv("CONNECT_SERVER_URL")) || nzchar(Sys.getenv("CONNECT_CONTENT_GUID"))
}

#' Register a Connect server and API key from `CONNECT_SERVER`/`CONNECT_API_KEY`.
#'
#' Returns the account and server names to deploy with, or `NULL` when the
#' variables are not both set. The key is passed straight to 'rsconnect'.
#' @noRd
.sashiny_connect_env_account <- function(rsconnect) {
  server_url <- Sys.getenv("CONNECT_SERVER", unset = "")
  api_key <- Sys.getenv("CONNECT_API_KEY", unset = "")
  if (!nzchar(server_url) || !nzchar(api_key)) {
    return(NULL)
  }
  server_name <- sub("^https?://", "", sub("/+$", "", server_url))
  server_name <- gsub("[^A-Za-z0-9._-]", "_", server_name)
  rsconnect$addServer(server_url, name = server_name, quiet = TRUE)
  rsconnect$connectApiUser(server = server_name, apiKey = api_key, quiet = TRUE)
  accounts <- rsconnect$accounts(server = server_name)
  list(account = accounts$name[[nrow(accounts)]], server = server_name)
}

#' The 'rsconnect' functions used for publishing (replaced in tests).
#' @noRd
.sashiny_rsconnect <- function() {
  .sashiny_need("rsconnect", "to publish to Posit Connect")
  list(
    deployApp = rsconnect::deployApp,
    addServer = rsconnect::addServer,
    connectApiUser = rsconnect::connectApiUser,
    accounts = rsconnect::accounts
  )
}

#' Publish a SAShiny app to Posit Connect
#'
#' Deploys an app directory (an `app.R` plus its SAS programs, contracts and
#' data) to Posit Connect with the 'rsconnect' package.
#'
#' @section Authentication:
#' Use either an account already registered with
#' [rsconnect::connectApiUser()] (pass `account` and/or `server`), or set the
#' environment variables `CONNECT_SERVER` (the server URL) and
#' `CONNECT_API_KEY`, which are registered for you. The API key is never
#' written to the bundle.
#'
#' @section 'SAS' credentials on Connect:
#' Credential files (`.authinfo`, `_authinfo`, `.netrc`, `.Renviron`, `.env`,
#' `*.pem`, `*.key`) are never bundled. The deployed app reads its 'SAS'
#' credentials from one of:
#' * the content's environment variables `SASHINY_SAS_USER` and
#'   `SASHINY_SAS_PASSWORD`. With `sas_credentials = "env"`, their values are
#'   taken from your current session and sent to Connect over an encrypted
#'   connection; they are not stored in the bundle.
#' * an `~/.authinfo` file managed by the Connect administrator for the
#'   content's run-as user (`sas_credentials = "server"`, nothing is sent).
#'
#' @section Licence:
#' Publishing requires `license_ack = TRUE`. This confirms that the deployed
#' app's users run programs on a 'SAS' system you are licensed to use, and
#' sets `SASHINY_LICENSE_ACK=true` on the content (spec section 6.6).
#'
#' @param app_dir The app directory. It must contain `app.R`.
#' @param title The content title shown on Connect.
#' @param name The content name (URL slug). Defaults to the directory name.
#' @param account,server A registered 'rsconnect' account and server. Ignored
#'   when `CONNECT_SERVER` and `CONNECT_API_KEY` are set.
#' @param sas_credentials `"env"` to send `SASHINY_SAS_USER` and
#'   `SASHINY_SAS_PASSWORD` from this session as Connect environment
#'   variables, or `"server"` to rely on an administrator-managed authinfo.
#' @param license_ack Must be `TRUE`; see the "Licence" section.
#' @param env_vars Names of further environment variables to send (for
#'   example `"SASHINY_VIYA_URL"`).
#' @param launch_browser Open the deployed app in a browser.
#' @param ... Further arguments passed to [rsconnect::deployApp()].
#' @return Invisibly, a list with `files` (bundled), `excluded` (credential
#'   files left out), `env_vars` (names sent) and `deployed` (the value of
#'   [rsconnect::deployApp()]).
#' @examples
#' \dontrun{
#' # Needs a Posit Connect server and an API key; not run during checks.
#' Sys.setenv(CONNECT_SERVER = "https://connect.example.com")
#' # CONNECT_API_KEY, SASHINY_SAS_USER and SASHINY_SAS_PASSWORD are best set
#' # in ~/.Renviron rather than in code.
#' sas_publish("my-app", title = "Cars explorer", license_ack = TRUE)
#' }
#' @export
sas_publish <- function(app_dir, title = NULL, name = NULL, account = NULL, server = NULL,
                        sas_credentials = c("env", "server"), license_ack = FALSE,
                        env_vars = character(0), launch_browser = FALSE, ...) {
  sas_credentials <- match.arg(sas_credentials)
  if (!isTRUE(license_ack)) {
    stop(
      "publishing requires license_ack = TRUE: confirm that the deployed app runs ",
      "programs only on a 'SAS' system you are licensed to use",
      call. = FALSE
    )
  }
  app_dir <- normalizePath(app_dir, winslash = "/", mustWork = TRUE)
  if (!file.exists(file.path(app_dir, "app.R"))) {
    stop("app_dir must contain app.R: ", app_dir, call. = FALSE)
  }
  vars <- c("SASHINY_LICENSE_ACK", env_vars)
  if (identical(sas_credentials, "env")) {
    missing <- c("SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD")
    missing <- missing[!nzchar(Sys.getenv(missing))]
    if (length(missing) > 0L) {
      stop(
        "sas_credentials = \"env\" needs ", paste(missing, collapse = " and "),
        " set in this session (for example in ~/.Renviron); or use ",
        "sas_credentials = \"server\"",
        call. = FALSE
      )
    }
    vars <- c(vars, "SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD")
  }
  vars <- unique(vars)
  bundle <- .sashiny_bundle_files(app_dir)
  if (length(bundle$excluded) > 0L) {
    message("Not bundled (credential files): ", paste(bundle$excluded, collapse = ", "))
  }
  rsconnect <- .sashiny_rsconnect()
  target <- .sashiny_connect_env_account(rsconnect) %||% list(account = account, server = server)

  # CRAN: rsconnect reads envVars values from this session. The
  # acknowledgement is set only for the deploy call and restored on exit.
  old <- Sys.getenv("SASHINY_LICENSE_ACK", unset = NA)
  Sys.setenv(SASHINY_LICENSE_ACK = "true")
  on.exit(
    if (is.na(old)) Sys.unsetenv("SASHINY_LICENSE_ACK") else Sys.setenv(SASHINY_LICENSE_ACK = old),
    add = TRUE
  )
  deployed <- rsconnect$deployApp(
    appDir = app_dir,
    appFiles = bundle$files,
    appName = name,
    appTitle = title,
    account = target$account,
    server = target$server,
    envVars = vars,
    launch.browser = launch_browser,
    ...
  )
  invisible(list(
    files = bundle$files, excluded = bundle$excluded, env_vars = vars, deployed = deployed
  ))
}

#' The "Publish to Posit Connect" panel of [sas_app()].
#' @noRd
.sashiny_publish_ui <- function(id) {
  ns <- shiny::NS(id)
  shiny::tagList(
    shiny::h4("Publish to Posit Connect"),
    shiny::p(
      "Deploys this app with 'rsconnect'. Credential files are never bundled.",
      "Set CONNECT_SERVER and CONNECT_API_KEY, or register an account with",
      "rsconnect::connectApiUser()."
    ),
    shiny::textInput(ns("app_dir"), "App directory", value = getwd()),
    shiny::textInput(ns("title"), "Title", value = ""),
    shiny::radioButtons(ns("sas_credentials"), "SAS credentials on Connect",
      choices = c(
        "Send SASHINY_SAS_USER / SASHINY_SAS_PASSWORD from this session" = "env",
        "Administrator-managed ~/.authinfo on the server" = "server"
      )
    ),
    shiny::checkboxInput(ns("license_ack"), paste(
      "I confirm that the deployed app runs programs only on a SAS system",
      "I am licensed to use."
    )),
    shiny::actionButton(ns("publish"), "Publish", class = "btn-primary"),
    shiny::verbatimTextOutput(ns("status"))
  )
}

#' The server of the publish panel.
#' @noRd
.sashiny_publish_server <- function(id, publish = sas_publish) {
  shiny::moduleServer(id, function(input, output, session) {
    status <- shiny::reactiveVal("")
    shiny::observeEvent(input$publish, {
      title <- if (nzchar(input$title %||% "")) input$title
      out <- tryCatch(
        {
          res <- publish(input$app_dir,
            title = title, sas_credentials = input$sas_credentials,
            license_ack = isTRUE(input$license_ack)
          )
          paste0(
            "Published ", length(res$files), " files.",
            if (length(res$excluded)) paste0(" Not bundled: ", paste(res$excluded, collapse = ", "))
          )
        },
        error = function(e) paste("Publish failed:", conditionMessage(e))
      )
      status(out)
    })
    output$status <- shiny::renderText(status())
  })
}

#' RStudio / Positron addin: publish a SAShiny app to Posit Connect
#'
#' Opens a small Shiny gadget that collects the app directory, title,
#' credential mode and licence acknowledgement, then calls [sas_publish()].
#' Registered in `inst/rstudio/addins.dcf`.
#'
#' @param app_dir The initial app directory.
#' @return Invisibly, `NULL`. Called for its side effect.
#' @examples
#' \dontrun{
#' # Interactive only: opens a gadget in the IDE viewer.
#' sas_publish_addin()
#' }
#' @export
sas_publish_addin <- function(app_dir = getwd()) {
  .sashiny_need("shiny", "to run the publish addin")
  ui <- shiny::fluidPage(.sashiny_publish_ui("publish"))
  server <- function(input, output, session) {
    shiny::updateTextInput(session, "publish-app_dir", value = app_dir)
    .sashiny_publish_server("publish")
  }
  viewer <- if (requireNamespace("rstudioapi", quietly = TRUE) && rstudioapi::isAvailable()) {
    shiny::paneViewer()
  } else {
    shiny::browserViewer()
  }
  shiny::runGadget(ui, server, viewer = viewer)
  invisible(NULL)
}
