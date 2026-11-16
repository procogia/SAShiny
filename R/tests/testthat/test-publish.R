# Tests for publishing to Posit Connect (spec section 6.7). No network: the
# 'rsconnect' functions are replaced with recording stubs.

publish_app_dir <- function() {
  dir <- tempfile("sashiny-app-")
  dir.create(file.path(dir, "data"), recursive = TRUE)
  dir.create(file.path(dir, ".git"))
  writeLines("library(SAShiny)", file.path(dir, "app.R"))
  writeLines("proc print; run;", file.path(dir, "prog.sas"))
  writeLines("a,b", file.path(dir, "data", "x.csv"))
  for (secret in c(".authinfo", "_authinfo", ".Renviron", ".env", "server.pem", "data/id.key")) {
    writeLines("secret", file.path(dir, secret))
  }
  writeLines("ref", file.path(dir, ".git", "HEAD"))
  dir
}

stub_rsconnect <- function(calls) {
  list(
    deployApp = function(...) {
      args <- list(...)
      args$ack_at_deploy <- Sys.getenv("SASHINY_LICENSE_ACK")
      calls$deploy <- args
      "deployed"
    },
    addServer = function(url, name, ...) calls$server <- c(url = url, name = name),
    connectApiUser = function(server, apiKey, ...) calls$api_key <- apiKey,
    accounts = function(server) data.frame(name = "api-user", server = server)
  )
}

test_that("sas_publish bundles no credential files and sends env var names only", {
  dir <- publish_app_dir()
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  calls <- new.env()
  local_mocked_bindings(.sashiny_rsconnect = function() stub_rsconnect(calls))
  withr::local_envvar(
    SASHINY_SAS_USER = "me", SASHINY_SAS_PASSWORD = "pw", SASHINY_LICENSE_ACK = NA,
    CONNECT_SERVER = NA, CONNECT_API_KEY = NA
  )
  expect_message(
    res <- sas_publish(dir, title = "Demo", license_ack = TRUE, account = "me", server = "srv"),
    "Not bundled"
  )
  expect_setequal(res$files, c("app.R", "prog.sas", "data/x.csv"))
  expect_setequal(
    res$excluded, c(".authinfo", "_authinfo", ".Renviron", ".env", "server.pem", "data/id.key")
  )
  expect_setequal(calls$deploy$appFiles, res$files)
  expect_identical(calls$deploy$envVars,
    c("SASHINY_LICENSE_ACK", "SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD"))
  expect_identical(calls$deploy$account, "me")
  expect_identical(calls$deploy$appTitle, "Demo")
  # The acknowledgement is set only for the deploy call, then restored.
  expect_identical(calls$deploy$ack_at_deploy, "true")
  expect_identical(Sys.getenv("SASHINY_LICENSE_ACK", unset = "unset"), "unset")
  expect_false(any(grepl("pw", unlist(calls$deploy), fixed = TRUE)))
})

test_that("sas_publish registers CONNECT_SERVER and CONNECT_API_KEY", {
  dir <- publish_app_dir()
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  calls <- new.env()
  local_mocked_bindings(.sashiny_rsconnect = function() stub_rsconnect(calls))
  withr::local_envvar(
    CONNECT_SERVER = "https://connect.example.com/", CONNECT_API_KEY = "k3y"
  )
  sas_publish(dir, sas_credentials = "server", license_ack = TRUE, account = "ignored")
  expect_identical(calls$server[["name"]], "connect.example.com")
  expect_identical(calls$api_key, "k3y")
  expect_identical(calls$deploy$account, "api-user")
  expect_identical(calls$deploy$server, "connect.example.com")
  expect_identical(calls$deploy$envVars, "SASHINY_LICENSE_ACK")
})

test_that("sas_publish refuses without a licence acknowledgement or credentials", {
  dir <- publish_app_dir()
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  local_mocked_bindings(.sashiny_rsconnect = function() stop("must not deploy"))
  expect_error(sas_publish(dir), "license_ack = TRUE")
  withr::local_envvar(SASHINY_SAS_USER = NA, SASHINY_SAS_PASSWORD = NA)
  expect_error(sas_publish(dir, license_ack = TRUE), "SASHINY_SAS_USER and SASHINY_SAS_PASSWORD")
  expect_error(sas_publish(tempdir(), license_ack = TRUE, sas_credentials = "server"), "app.R")
})

test_that("the publish tab is opt-in and hidden on Posit Connect", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  path <- file.path(.sashiny_fixtures(), "contracts", "valid", "minimal", "contract.sashiny.yml")
  html <- function(app) {
    ui <- get("ui", environment(app$httpHandler))
    paste(as.character(if (is.function(ui)) ui(NULL) else ui), collapse = "")
  }
  withr::local_envvar(RSTUDIO_PRODUCT = NA, CONNECT_SERVER_URL = NA, CONNECT_CONTENT_GUID = NA)
  expect_false(grepl("Publish to Posit Connect", html(sas_app(list(path), .sashiny_engine_mock()))))
  expect_true(grepl("Publish to Posit Connect",
    html(sas_app(list(path), .sashiny_engine_mock(), publish = TRUE))))
  withr::local_envvar(RSTUDIO_PRODUCT = "CONNECT")
  expect_false(grepl("Publish to Posit Connect",
    html(sas_app(list(path), .sashiny_engine_mock(), publish = TRUE))))
})

test_that("the publish panel reports success and failure", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  calls <- new.env()
  fake <- function(app_dir, ...) {
    calls$args <- list(app_dir = app_dir, ...)
    if (!isTRUE(calls$args$license_ack)) stop("publishing requires license_ack = TRUE")
    list(files = c("app.R", "p.sas"), excluded = ".authinfo")
  }
  shiny::testServer(.sashiny_publish_server, args = list(publish = fake), {
    session$setInputs(app_dir = "x", title = "", sas_credentials = "server", license_ack = FALSE)
    session$setInputs(publish = 1)
    expect_match(output$status, "Publish failed: publishing requires")
    session$setInputs(license_ack = TRUE, publish = 2)
    expect_match(output$status, "Published 2 files. Not bundled: .authinfo", fixed = TRUE)
    expect_null(calls$args$title)
  })
})
