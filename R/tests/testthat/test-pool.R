# Tests for the bounded session pool (issue #7).

test_that("pool runs a contract", {
  pool <- sas_pool(sas_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_pool_run(pool, contract, list(), today = .sashiny_today)
  expect_identical(result$status, "success")
  sas_pool_close(pool)
})

test_that("pool reuses a session", {
  pool <- sas_pool(sas_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  sas_pool_run(pool, contract, list(), today = .sashiny_today)
  sas_pool_run(pool, contract, list(), today = .sashiny_today)
  expect_length(pool$sessions, 1L)
  expect_identical(pool$sessions[[1]]$runs, 2L)
  sas_pool_close(pool)
})

test_that("pool discards a session on error", {
  pool <- sas_pool(sas_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_pool_run(pool, contract, list(min_msrp = "bad"),
                         today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_length(pool$sessions, 0L)
  sas_pool_close(pool)
})