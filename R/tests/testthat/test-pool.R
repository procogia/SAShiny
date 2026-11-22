# Tests for the bounded session pool (issue #7).

test_that("pool runs a contract", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_run(contract, pool, list(), today = .sashiny_today)
  expect_identical(result$status, "success")
  sas_close(pool)
})

test_that("pool reuses a session", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  sas_run(contract, pool, list(), today = .sashiny_today)
  sas_run(contract, pool, list(), today = .sashiny_today)
  expect_length(pool$sessions, 1L)
  expect_identical(pool$sessions[[1]]$runs, 2L)
  sas_close(pool)
})

test_that("pool keeps the session on an input validation error", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_run(contract, pool, list(min_msrp = "bad"),
                         today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_length(pool$sessions, 1L)
  sas_close(pool)
})

test_that("pool discards and closes a factory session after a SAS failure", {
  closed <- 0L
  make_engine <- function() {
    test_saspy_engine(list(), session_factory = function() {
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

test_that("pool discard clears the pool choices cache (spec section 6.4, #152)", {
  make_engine <- function() {
    test_saspy_engine(list(), session_factory = function() {
      list(
        submit = function(code, results = "TEXT") stop("lost connection"),
        endsas = function() NULL
      )
    })
  }
  pool <- sas_pool(make_engine, max_size = 1L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  old <- list(pick = list(list(value = "old", label = "old")))
  .sashiny_store_choices(pool, contract, old)
  expect_identical(.sashiny_cached_choices(pool, contract), old)
  result <- sas_engine_run(pool, contract, list(), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_null(.sashiny_cached_choices(pool, contract))
})

test_that("pool keeps the choices cache on an input validation error", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 1L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  old <- list(pick = list(list(value = "old", label = "old")))
  .sashiny_store_choices(pool, contract, old)
  result <- sas_run(contract, pool, list(min_msrp = "bad"), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_identical(.sashiny_cached_choices(pool, contract), old)
  sas_close(pool)
})

test_that("a factory pool gives each session its own engine", {
  pool <- sas_pool(function() .sashiny_engine_mock(), max_size = 2L, acquire_timeout = 0.05)
  a <- .sashiny_acquire(pool)
  b <- .sashiny_acquire(pool)
  expect_length(pool$sessions, 2L)
  # Every session is busy: acquire waits then returns NULL (spec section 6.5).
  expect_null(.sashiny_acquire(pool))
  .sashiny_release(pool, a)
  .sashiny_release(pool, b)
  sas_close(pool)
  expect_length(pool$sessions, 0L)
})

test_that("pool warms min_size sessions", {
  made <- 0L
  pool <- sas_pool(function() {
    made <<- made + 1L
    .sashiny_engine_mock()
  }, min_size = 2L, max_size = 3L)
  expect_identical(made, 2L)
  expect_length(pool$sessions, 2L)
  sas_close(pool)
})

test_that("pool rejects invalid bounds", {
  expect_error(sas_pool(.sashiny_engine_mock(), min_size = 3L, max_size = 2L), "min_size")
  expect_error(sas_pool(.sashiny_engine_mock(), min_size = -1L), "non-negative")
  # Inf == floor(Inf), so a non-finite size must be rejected explicitly (#94).
  expect_error(sas_pool(.sashiny_engine_mock(), max_size = Inf), "whole numbers")
  expect_error(sas_pool(.sashiny_engine_mock(), max_size = NaN))
})

test_that("pool returns an error result when exhausted (spec section 6.5)", {
  pool <- sas_pool(function() .sashiny_engine_mock(), max_size = 1L, acquire_timeout = 0.05)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  a <- .sashiny_acquire(pool)
  result <- sas_run(contract, pool, list(), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "pool exhausted")
  .sashiny_release(pool, a)
  sas_close(pool)
})

test_that("pool close stops creating sessions (issue #80)", {
  made <- 0L
  pool <- sas_pool(function() {
    made <<- made + 1L
    .sashiny_engine_mock()
  }, min_size = 2L, max_size = 4L)
  expect_identical(made, 2L)
  sas_close(pool)
  # After close, no new sessions may be created.
  expect_identical(made, 2L)
  expect_length(pool$sessions, 0L)
})

test_that("pool run after close returns an error result (issue #80)", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 2L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  sas_close(pool)
  result <- sas_run(contract, pool, list(), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "pool exhausted")
})

test_that("pool factory failure returns an error result (issue #75)", {
  pool <- sas_pool(function() stop("connection refused"), min_size = 0L, max_size = 1L)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_run(contract, pool, list(), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "connection refused")
})
