# Tests for the runner layer.

test_that("sas_run accepts a contract object", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_run(contract, list(), sas_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run accepts a contract path", {
  path <- file.path(.sashiny_fixtures(), "contracts", "valid",
                    "minimal", "contract.sashiny.yml")
  result <- sas_run(path, list(), sas_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run reports invalid values", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_run(contract, list(min_msrp = "bad"), sas_engine_mock(),
                    today = .sashiny_today)
  expect_identical(result$status, "error")
})