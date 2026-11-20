# Persistent SAS workers (spec section 6.5, "Session lifetime"; #130 J1/J2).
# No SAS: the worker runs a fake saspy session in a callr child.

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

.sashiny_skip_worker <- function() {
  skip_on_cran()
  skip_if_not_installed("callr")
  skip_if_not_installed("later")
  skip_if_not_installed("promises")
  # The worker process loads the installed package.
  skip_if(
    length(find.package("SAShiny", lib.loc = .libPaths(), quiet = TRUE)) == 0L,
    "SAShiny is not installed"
  )
}

# A serialisable fake factory (top-level, no captured state). `delay` seconds
# per main submission, read from an environment variable set in the child.
.sashiny_worker_factory <- function() {
  fake <- new.env()
  fake$ended <- FALSE
  fake$pid <- Sys.getpid()
  fake$submit <- function(code, results = "HTML") {
    run <- regmatches(code, regexpr("SASHINY-BEGIN run=[^ ;\"']+", code))
    if (length(run) == 0L) {
      return(list(LOG = "", LST = ""))
    }
    Sys.sleep(as.numeric(Sys.getenv("SASHINY_TEST_DELAY", "0")))
    id <- sub("SASHINY-BEGIN run=", "", run)
    list(
      LOG = paste0(
        "SXPID=", fake$pid, "\nNOTE: SASHINY-BEGIN run=", id, "\nNOTE: SASHINY-BEGIN-PROGRAM\n",
        "NOTE: SASHINY-END-PROGRAM\nNOTE: SASHINY-END run=", id, " syscc=0\n"
      ),
      LST = ""
    )
  }
  fake$sd2df <- function(...) NULL
  fake$df2sd <- function(...) NULL
  fake$download <- function(...) list(Success = FALSE, LOG = "")
  fake$endsas <- function() fake$ended <- TRUE
  fake
}

worker_contract <- function(timeout = NULL) {
  dir <- tempfile("sashiny-worker-")
  dir.create(dir)
  writeLines("data work.out; n = 1; run;", file.path(dir, "program.sas"))
  lines <- c("sashiny: 1", "program: program.sas", "title: Worker", "outputs:",
    "  log:", "    type: log")
  if (!is.null(timeout)) lines <- c(lines, "run:", paste0("  timeout_seconds: ", timeout))
  writeLines(lines, file.path(dir, "contract.sashiny.yml"))
  sas_contract(file.path(dir, "contract.sashiny.yml"))
}

worker_engine <- function() {
  engine <- test_saspy_engine(list(java = "java"), session_factory = .sashiny_worker_factory)
  engine$use_worker <- TRUE
  engine
}

worker_pid <- function(result) sub("^SXPID=", "", regmatches(result$log, regexpr("SXPID=[0-9]+", result$log)))

test_that("an engine reuses one worker and one SAS session across runs", {
  .sashiny_skip_worker()
  engine <- worker_engine()
  on.exit(sas_engine_close(engine), add = TRUE)
  contract <- worker_contract()
  runs <- lapply(1:3, function(i) sas_engine_run(engine, contract, list(), today = .sashiny_today))
  expect_true(all(vapply(runs, function(r) r$status, "") == "success"))
  expect_length(unique(vapply(runs, function(r) r$metadata$worker_id, "")), 1L)
  expect_length(unique(vapply(runs, worker_pid, "")), 1L)
  expect_false(identical(worker_pid(runs[[1]]), as.character(Sys.getpid())))
  expect_identical(engine$worker$starts, 1L)
})

test_that("a timeout kills the worker and the next run starts a new one", {
  .sashiny_skip_worker()
  withr::local_envvar(SASHINY_TEST_DELAY = "3")
  engine <- worker_engine()
  on.exit(sas_engine_close(engine), add = TRUE)
  t0 <- proc.time()[["elapsed"]]
  slow <- sas_engine_run(engine, worker_contract(timeout = 1), list(), today = .sashiny_today)
  expect_lt(proc.time()[["elapsed"]] - t0, 10)
  expect_identical(slow$status, "error")
  expect_match(slow$metadata$engine_error, "timeout_seconds=1")
  expect_null(engine$worker$rs)
  withr::local_envvar(SASHINY_TEST_DELAY = "0")
  ok <- sas_engine_run(engine, worker_contract(), list(), today = .sashiny_today)
  expect_identical(ok$status, "success")
  expect_identical(engine$worker$starts, 2L)
})

test_that("the event loop keeps running during a worker run", {
  .sashiny_skip_worker()
  withr::local_envvar(SASHINY_TEST_DELAY = "2")
  engine <- worker_engine()
  on.exit(sas_engine_close(engine), add = TRUE)
  contract <- worker_contract()
  ticks <- 0L
  ticking <- TRUE
  tick <- function() {
    ticks <<- ticks + 1L
    if (ticking) later::later(tick, 0.01)
  }
  later::later(tick, 0)
  on.exit(ticking <- FALSE, add = TRUE)
  state <- .sashiny_await(.sashiny_run_async(engine, contract, list(), today = .sashiny_today))
  ticking <- FALSE
  later::run_now(0.05)
  expect_identical(state$value$status, "success")
  # Other callbacks ran while the worker was busy (a blocked loop gives 0).
  expect_gt(ticks, 3L)
})

test_that("an async timeout resolves to an error and replaces the worker", {
  .sashiny_skip_worker()
  withr::local_envvar(SASHINY_TEST_DELAY = "5")
  engine <- worker_engine()
  on.exit(sas_engine_close(engine), add = TRUE)
  state <- .sashiny_await(.sashiny_run_async(engine, worker_contract(timeout = 1), list(),
    today = .sashiny_today))
  expect_identical(state$value$status, "error")
  expect_match(state$value$metadata$engine_error, "timeout_seconds=1")
  expect_null(engine$worker$rs)
})

test_that("a pool runs on persistent workers and keeps its limits without blocking", {
  .sashiny_skip_worker()
  withr::local_envvar(SASHINY_TEST_DELAY = "1")
  pool <- sas_pool(worker_engine, max_size = 1L, acquire_timeout = 0.2)
  on.exit(sas_engine_close(pool), add = TRUE)
  contract <- worker_contract()
  first <- .sashiny_run_async(pool, contract, list(), today = .sashiny_today)
  second <- .sashiny_run_async(pool, contract, list(), today = .sashiny_today)
  s2 <- .sashiny_await(second)
  s1 <- .sashiny_await(first)
  expect_identical(s1$value$status, "success")
  expect_identical(s2$value$status, "error")
  expect_match(s2$value$metadata$engine_error, "pool exhausted: all 1 sessions busy")
  withr::local_envvar(SASHINY_TEST_DELAY = "0")
  again <- .sashiny_await(.sashiny_run_async(pool, contract, list(), today = .sashiny_today))
  expect_identical(again$value$worker_id %||% again$value$metadata$worker_id,
    s1$value$metadata$worker_id)
})

test_that("ending the browser session cancels an in-flight run (#50)", {
  .sashiny_skip_worker()
  withr::local_envvar(SASHINY_TEST_DELAY = "5")
  engine <- worker_engine()
  on.exit(sas_engine_close(engine), add = TRUE)
  ended <- NULL
  session <- list(onSessionEnded = function(f) {
    ended <<- f
    function() NULL
  })
  p <- .sashiny_run_async(engine, worker_contract(), list(), today = .sashiny_today,
    session = session)
  later::run_now(0.5)
  ended()
  state <- .sashiny_await(p)
  expect_identical(state$value$status, "error")
  expect_match(state$value$metadata$engine_error, "browser session ended")
  expect_null(engine$worker$rs)
})

test_that("engines without a SAS session run in-process", {
  skip_if_not_installed("promises")
  skip_if_not_installed("later")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  state <- .sashiny_await(.sashiny_run_async(.sashiny_engine_mock(), contract, list(),
    today = .sashiny_today, run_id = "m-1"))
  expect_identical(state$value$run_id, "m-1")
  expect_identical(state$value$status, "success")
  hook <- test_saspy_engine(list(), session_factory = function() NULL)
  expect_false(.sashiny_uses_worker(hook, contract))
  expect_true(.sashiny_uses_worker(test_saspy_engine(list()), contract))
  contract$data$run$timeout_seconds <- 2
  expect_true(.sashiny_uses_worker(hook, contract))
})
