# Classed errors, print() and sas_check() (#130 H5).

fake_result <- function(status = "success", log = "", outputs = list(), metadata = list()) {
  structure(list(run_id = "r-123", status = status, outputs = outputs, log = log,
    metadata = c(list(engine = "mock", backend = "oda", seconds = 1.5), metadata)),
    class = "sashiny_result")
}

test_that("raised errors carry sashiny_error and a kind class", {
  expect_error(sas_result_table(fake_result(), "nope"), class = "sashiny_error_values")
  expect_error(sas_result_table(fake_result(), "nope"), class = "sashiny_error")
  expect_error(outside_tests(.sashiny_check_engine(list())), class = "sashiny_error_engine")
  expect_error(sas_deploy_targets_lookup <- .sashiny_lookup_target("nope"),
    class = "sashiny_error_deploy")
  e <- tryCatch(.sashiny_upload_error("too big"), error = function(e) e)
  expect_s3_class(e, c("sashiny_upload_error", "sashiny_error_upload", "sashiny_error"))
})

test_that("cli never interprets braces in user values", {
  e <- tryCatch(.sashiny_abort("values", "bad {value} in {.file x}"), error = function(e) e)
  expect_identical(conditionMessage(e), "bad {value} in {.file x}")
})

test_that("an invalid contract names the file and each path", {
  dir <- tempfile("sashiny-bad-")
  dir.create(dir)
  writeLines("data a; run;", file.path(dir, "p.sas"))
  writeLines(c("sashiny: 1", "program: p.sas", "title: Cars", "inputs:", "  min_msrp:", "    type: numeric",
    "    label: Min", "    min: 10", "    max: 1", "outputs:", "  log:", "    type: log"),
    file.path(dir, "cars.sashiny.yml"))
  contract <- sas_contract(file.path(dir, "cars.sashiny.yml"))
  e <- tryCatch(sas_validate(contract, error = TRUE), error = function(e) e)
  expect_s3_class(e, "sashiny_error_contract")
  expect_match(conditionMessage(e), "cars.sashiny.yml is invalid", fixed = TRUE)
  expect_match(conditionMessage(e), "/inputs/min_msrp", fixed = TRUE)
  expect_true(length(e$issues) >= 1L)
  good <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "minimal",
    "contract.sashiny.yml"))
  expect_identical(sas_validate(good, error = TRUE), good)
})

test_that("sas_check() passes success and warning, and raises run errors", {
  ok <- fake_result()
  expect_identical(sas_check(ok), ok)
  expect_invisible(sas_check(fake_result("warning")))
  bad <- fake_result("error", log = "NOTE: start\nERROR: File WORK.X does not exist.\nERROR: again\n")
  e <- tryCatch(sas_check(bad), error = function(e) e)
  expect_s3_class(e, c("sashiny_error_run", "sashiny_error"))
  expect_identical(conditionMessage(e),
    "run r-123 failed: ERROR: File WORK.X does not exist. (log line 2)")
  expect_identical(e$result, bad)
  engine <- fake_result("error", metadata = list(engine_error = "run exceeded timeout_seconds=1"))
  expect_error(sas_check(engine), "run r-123 failed: run exceeded timeout_seconds=1", fixed = TRUE)
  invalid <- fake_result("error", metadata = list(issues = list(list(code = "V003", input = "/inputs/x"))))
  expect_error(sas_check(invalid), "invalid input V003 /inputs/x", fixed = TRUE)
})

test_that("print() shows status, run id, duration, backend, reason and outputs", {
  withr::local_options(cli.num_colors = 1)
  res <- fake_result("error",
    log = "NOTE: a\nERROR: boom\n",
    outputs = list(
      stats = list(columns = list(list(name = "n")), rows = list(list(1), list(2)),
        total_rows = 50L, truncated = TRUE, formatted = FALSE),
      log = list(list(level = "error", text = "ERROR: boom")),
      report = "<html></html>",
      csv = list(filename = "x.csv", mime = "text/csv", data = ""),
      missing = list(error = "dataset WORK.NOPE not found")
    ))
  expect_snapshot(print(res))
  expect_identical(format(res)[[1]], "<sashiny result> error")
})
