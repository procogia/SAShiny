# Tests for the app layer.

test_that("sas_app builds a multi-program app", {
  contracts <- list(
    sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                           "minimal", "contract.sashiny.yml")),
    sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                           "numeric", "contract.sashiny.yml"))
  )
  app <- sas_app(contracts, sas_engine_mock())
  expect_s3_class(app, "shiny.appobj")
})

test_that("sas_app accepts paths", {
  paths <- list(
    file.path(.sashiny_fixtures(), "contracts", "valid",
              "minimal", "contract.sashiny.yml"),
    file.path(.sashiny_fixtures(), "contracts", "valid",
              "numeric", "contract.sashiny.yml")
  )
  app <- sas_app(paths, sas_engine_mock())
  expect_s3_class(app, "shiny.appobj")
})