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
test_that("contract_sha256 hashes the YAML bytes and program_sha256 the program (spec section 8)", {
  path <- file.path(.sashiny_fixtures(), "contracts", "valid", "minimal", "contract.sashiny.yml")
  contract <- sas_contract(path)
  res <- sas_engine_run(sas_engine_mock(), contract, list(), today = as.Date("2026-11-11"))
  yaml_bytes <- readBin(path, "raw", n = file.info(path)$size)
  prog <- file.path(dirname(path), "program.sas")
  prog_bytes <- readBin(prog, "raw", n = file.info(prog)$size)
  expect_identical(res$metadata$contract_sha256, unclass(as.character(openssl::sha256(yaml_bytes))))
  expect_identical(res$metadata$program_sha256, unclass(as.character(openssl::sha256(prog_bytes))))
  expect_false(identical(res$metadata$contract_sha256, res$metadata$program_sha256))
})

test_that("mock engine reports V014 for a missing upload (spec section 7)", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "dataset", "contract.sashiny.yml"))
  result <- sas_engine_run(sas_engine_mock(), contract, list(),
                           uploads = list(adsl = "/nonexistent/path.csv"))
  expect_identical(result$status, "error")
  expect_identical(result$metadata$issues[[1]]$code, "V014")
  expect_match(result$metadata$issues[[1]]$message, "file not found")
})

test_that("mock engine reports V014 for a bad extension (spec section 7)", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "dataset", "contract.sashiny.yml"))
  result <- sas_engine_run(sas_engine_mock(), contract, list(),
                           uploads = list(adsl = "sample.txt"))
  expect_identical(result$status, "error")
  expect_identical(result$metadata$issues[[1]]$code, "V014")
  expect_match(result$metadata$issues[[1]]$message, "not accepted")
})

test_that("recordings round-trip full-precision numbers (spec section 8.3)", {
  dir <- tempfile("sashiny-mock-")
  dir.create(dir)
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  engine <- sas_engine_mock(recordings_dir = dir)
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  big <- 2^53 + 2  # not representable in 15 significant digits
  sas_engine_record(engine, contract, list(), list(
    status = "success", log = "",
    outputs = list(log = list(list(text = "x", level = "text", value = big)))
  ))
  key <- .sashiny_recording_key(contract, list())
  raw <- jsonlite::fromJSON(file.path(dir, paste0(key, ".json")), simplifyVector = FALSE)
  expect_identical(raw$outputs$log[[1]]$value, big)
})
