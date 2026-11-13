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

test_that("pool keeps the session on an input validation error", {
  pool <- sas_pool(sas_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_pool_run(pool, contract, list(min_msrp = "bad"),
                         today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_length(pool$sessions, 1L)
  sas_pool_close(pool)
})

test_that("pool discards and closes a factory session after a SAS failure", {
  closed <- 0L
  make_engine <- function() {
    sas_engine_saspy(list(), session_factory = function() {
      list(
        submit = function(code, results = "TEXT") stop("lost connection"),
        endsas = function() closed <<- closed + 1L
      )
    })
  }
  pool <- sas_pool(make_engine, max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_engine_run(pool, contract, list(), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "lost connection")
  expect_length(pool$sessions, 0L)
})

test_that("a factory pool gives each session its own engine", {
  pool <- sas_pool(function() sas_engine_mock(), max_size = 2L)
  a <- .sashiny_acquire(pool)
  b <- .sashiny_acquire(pool)
  expect_length(pool$sessions, 2L)
  expect_error(.sashiny_acquire(pool), "pool exhausted")
  .sashiny_release(pool, a)
  .sashiny_release(pool, b)
  sas_pool_close(pool)
  expect_length(pool$sessions, 0L)
})

test_that("pool warms min_size sessions", {
  made <- 0L
  pool <- sas_pool(function() {
    made <<- made + 1L
    sas_engine_mock()
  }, min_size = 2L, max_size = 3L)
  expect_identical(made, 2L)
  expect_length(pool$sessions, 2L)
  sas_pool_close(pool)
})

test_that("pool rejects invalid bounds", {
  expect_error(sas_pool(sas_engine_mock(), min_size = 3L, max_size = 2L), "min_size")
  expect_error(sas_pool(sas_engine_mock(), min_size = -1L), "non-negative")
})
