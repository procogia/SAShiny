# Tests for the mock engine (issue #5).

test_that("mock engine returns empty success without recordings", {
  engine <- sas_engine_mock()
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_engine_run(engine, contract, list(), today = .sashiny_today)
  expect_identical(result$status, "success")
  expect_true(nzchar(result$run_id))
  expect_identical(result$metadata$engine, "mock")
})

test_that("mock engine reports error for invalid values", {
  engine <- sas_engine_mock()
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_engine_run(engine, contract, list(min_msrp = "not-a-number"),
                           today = .sashiny_today)
  expect_identical(result$status, "error")
})

test_that("mock engine replays a recording", {
  dir <- tempfile("sashiny-mock-")
  dir.create(dir)
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  engine <- sas_engine_mock(recordings_dir = dir)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  macros <- list()
  key <- .sashiny_recording_key(contract, macros)
  recording <- list(
    status = "warning",
    log = "NOTE: SASHINY-BEGIN run=fixture;\nWARNING: something\n",
    outputs = list(log = list(list(text = "WARNING: something", level = "warning"))),
    sas_version = "9.04.01M8"
  )
  writeLines(jsonlite::toJSON(recording, auto_unbox = TRUE, null = "null"),
             file.path(dir, paste0(key, ".json")))

  result <- sas_engine_run(engine, contract, list(), today = .sashiny_today)
  expect_identical(result$status, "warning")
  expect_identical(result$log, recording$log)
  expect_identical(result$metadata$sas_version, "9.04.01M8")
})

test_that("mock engine saves a recording", {
  dir <- tempfile("sashiny-mock-")
  dir.create(dir)
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  engine <- sas_engine_mock(recordings_dir = dir)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  macros <- list()
  sas_engine_record(engine, contract, macros, list(status = "success", log = ""))
  key <- .sashiny_recording_key(contract, macros)
  expect_true(file.exists(file.path(dir, paste0(key, ".json"))))
})