# Tests for the app layer.

test_that("sas_app builds a multi-program app", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  a <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                              "minimal", "contract.sashiny.yml"))
  b <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                              "numeric", "contract.sashiny.yml"))
  # Both fixtures use `program.sas`, so give them distinct explicit ids.
  a$data$id <- "minimal"
  b$data$id <- "numeric"
  app <- sas_app(list(a, b), sas_engine_mock())
  expect_s3_class(app, "shiny.appobj")
})

test_that("sas_app accepts paths", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  paths <- list(
    file.path(.sashiny_fixtures(), "contracts", "valid",
              "minimal", "contract.sashiny.yml")
  )
  app <- sas_app(paths, sas_engine_mock())
  expect_s3_class(app, "shiny.appobj")
})

test_that("sas_app rejects duplicate module ids", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  a <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                              "minimal", "contract.sashiny.yml"))
  b <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                              "numeric", "contract.sashiny.yml"))
  # Both derive to `program` from their `program.sas` file name.
  expect_error(sas_app(list(a, b), sas_engine_mock()), "duplicate module id")
})

test_that("default module id is derived from the program file name (spec section 2)", {
  expect_identical(.sashiny_default_module_id("Cars Explorer.sas"), "cars_explorer")
  expect_identical(.sashiny_default_module_id("2nd-report.sas"), "p_2nd_report")
  expect_identical(.sashiny_default_module_id("Report.SAS"), "report")
  expect_identical(.sashiny_default_module_id(paste0(strrep("a", 40), ".sas")), strrep("a", 32))
})

test_that("default module id lower-cases a capital dotted I to a plain i (issue #63)", {
  expect_identical(.sashiny_default_module_id("\u0130stanbul.sas"), "istanbul")
})