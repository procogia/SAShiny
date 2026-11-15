# Tests for the non-blocking background run used by the Shiny module (issue #44).

.sashiny_await <- function(p, timeout = 30) {
  state <- new.env()
  state$done <- FALSE
  promises::then(p,
    onFulfilled = function(value) {
      state$value <- value
      state$done <- TRUE
    },
    onRejected = function(e) {
      state$error <- e
      state$done <- TRUE
    }
  )
  deadline <- Sys.time() + timeout
  while (!state$done && Sys.time() < deadline) {
    later::run_now(0.05)
  }
  state
}

.sashiny_skip_bg <- function() {
  skip_on_cran()
  skip_if_not_installed("callr")
  skip_if_not_installed("later")
  skip_if_not_installed("promises")
  # The background process loads the installed package.
  skip_if(!nzchar(system.file(package = "SAShiny")), "SAShiny is not installed")
}

test_that("only mock and saspy engines are sent to a background process", {
  expect_identical(.sashiny_portable_engine(sas_engine_mock()), sas_engine_mock())
  live <- sas_engine_saspy(list(java = "java"))
  live$sas <- "a live session"
  copy <- .sashiny_portable_engine(live)
  expect_s3_class(copy, "sashiny_engine_saspy")
  expect_null(copy$sas)
  expect_identical(copy$cfg, live$cfg)
  expect_null(.sashiny_portable_engine(sas_pool(sas_engine_mock())))
  custom <- structure(list(), class = c("my_engine", "sashiny_engine_mock"))
  expect_null(.sashiny_portable_engine(custom))
})

test_that("the run deadline matches the saspy engine's rule", {
  contract <- list(data = list(run = list()))
  expect_identical(.sashiny_run_deadline(sas_engine_mock(), contract), Inf)
  expect_identical(.sashiny_run_deadline(sas_engine_saspy(list()), contract), 300)
  hook <- sas_engine_saspy(list(), session_factory = function() NULL)
  expect_identical(.sashiny_run_deadline(hook, contract), Inf)
  contract$data$run$timeout_seconds <- 2
  expect_identical(.sashiny_run_deadline(hook, contract), 2)
})

test_that("a background run resolves without blocking the event loop", {
  .sashiny_skip_bg()
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  ticks <- 0L
  ticking <- TRUE
  tick <- function() {
    ticks <<- ticks + 1L
    if (ticking) later::later(tick, 0.01)
  }
  later::later(tick, 0)
  # Stop the ticker even on failure, so it cannot keep the global loop busy.
  on.exit(ticking <- FALSE, add = TRUE)
  p <- .sashiny_run_bg_promise(sas_engine_mock(), contract, list(),
    today = .sashiny_today, run_id = "bg-1"
  )
  expect_true(promises::is.promise(p))
  state <- .sashiny_await(p)
  ticking <- FALSE
  later::run_now(0.05)
  expect_true(state$done)
  expect_null(state$error)
  expect_s3_class(state$value, "sashiny_result")
  expect_identical(state$value$run_id, "bg-1")
  expect_identical(state$value$status, "success")
  # Other callbacks ran while the child process was working.
  expect_gt(ticks, 1L)
})

test_that("a background saspy run past timeout_seconds resolves to an error (issue #97)", {
  .sashiny_skip_bg()
  dir <- tempfile("sashiny-bg-timeout-")
  dir.create(dir)
  writeLines("data work.out; n = 1; run;", file.path(dir, "program.sas"))
  writeLines(c(
    "sashiny: 1", "program: program.sas", "title: Timeout",
    "outputs:", "  log:", "    type: log",
    "run:", "  timeout_seconds: 1"
  ), file.path(dir, "contract.sashiny.yml"))
  contract <- sas_contract(file.path(dir, "contract.sashiny.yml"))
  slow <- function() {
    Sys.sleep(30)
    NULL
  }
  engine <- sas_engine_saspy(list(java = "java"), session_factory = slow)
  started <- proc.time()[["elapsed"]]
  state <- .sashiny_await(.sashiny_run_bg_promise(engine, contract, list(), today = .sashiny_today))
  elapsed <- proc.time()[["elapsed"]] - started
  expect_null(state$error)
  expect_identical(state$value$status, "error")
  expect_match(state$value$metadata$engine_error, "timeout_seconds=1")
  expect_lt(elapsed, 10)
})

test_that("a failing background run rejects the promise", {
  .sashiny_skip_bg()
  contract <- structure(list(data = list(), base_dir = tempdir(), path = "missing"),
    class = "sashiny_contract"
  )
  state <- .sashiny_await(.sashiny_run_bg_promise(sas_engine_mock(), contract, list()))
  expect_true(state$done)
  expect_s3_class(state$error, "error")
})
