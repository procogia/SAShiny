# Tests for the runner layer.

test_that("sas_run accepts a contract object", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_run(contract, .sashiny_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run accepts a contract path", {
  path <- file.path(.sashiny_fixtures(), "contracts", "valid",
                    "minimal", "contract.sashiny.yml")
  result <- sas_run(path, .sashiny_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run reports invalid values", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_run(contract, .sashiny_engine_mock(), list(min_msrp = "bad"),
                    today = .sashiny_today)
  expect_identical(result$status, "error")
})
test_that("the old names and argument order still work, with deprecation warnings", {
  withr::local_options(lifecycle_verbosity = "warning")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "minimal",
    "contract.sashiny.yml"))
  engine <- .sashiny_engine_mock()
  expect_warning(old <- sas_run(contract, list(), engine, today = .sashiny_today),
    class = "lifecycle_warning_deprecated")
  expect_identical(old$status, "success")
  pool <- sas_pool(engine)
  expect_warning(res <- sas_pool_run(pool, contract, list(), today = .sashiny_today),
    class = "lifecycle_warning_deprecated")
  expect_identical(res$status, "success")
  expect_warning(sas_pool_close(pool), class = "lifecycle_warning_deprecated")
  data <- list(sashiny = 1L, program = "p.sas", title = "t", outputs = list(log = list(type = "log")))
  expect_warning(lints <- sashiny_lint(data, "run;"), class = "lifecycle_warning_deprecated")
  expect_identical(lints, sas_lint(data, "run;"))
})

test_that("the new forms do not warn", {
  withr::local_options(lifecycle_verbosity = "warning")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "minimal",
    "contract.sashiny.yml"))
  pool <- sas_pool(.sashiny_engine_mock())
  expect_no_warning(sas_run(contract, pool, today = .sashiny_today))
  expect_no_warning(sas_close(pool))
})
