# Tests for the contract-as-tool experiment (mock engine only).
# Run: Rscript -e "testthat::test_dir('experiments/sashiny-tools/R/tests')"

library(testthat)
Sys.setenv(TESTTHAT = "true")
root <- normalizePath(file.path(dirname(sys.frame(1)$ofile %||% "."), "..", "..", ".."),
  mustWork = FALSE)
if (!file.exists(file.path(root, "spec"))) root <- normalizePath("../../../..")
pkgload::load_all(file.path(root, "R"), quiet = TRUE, export_all = FALSE)
source(file.path(root, "experiments", "sashiny-tools", "R", "sashiny_tools.R"))
fix <- file.path(root, "spec", "fixtures", "contracts", "valid")
mock <- SAShiny:::.sashiny_engine_mock
load_fix <- function(name) SAShiny::sas_contract(file.path(fix, name, "contract.sashiny.yml"))
today <- as.Date("2026-11-11")

test_that("name and description", {
  cars <- SAShiny::sas_contract(file.path(root, "examples", "general", "cars_explorer.sashiny.yml"))
  expect_identical(tool_name(cars), "cars_explorer")
  tool <- sas_as_tool(cars, mock())
  expect_identical(tool@name, "cars_explorer")
  expect_match(tool@description, "Car price explorer")
})

test_that("each input type maps to an ellmer type", {
  num <- tool_arguments(load_fix("numeric"), today)
  expect_s3_class(num$min_msrp, "ellmer::TypeBasic")
  expect_identical(num$min_msrp@type, "integer")
  expect_match(num$min_msrp@description, "max 200000")
  expect_identical(num$ratio@type, "number")
  multi <- tool_arguments(load_fix("multichoice"), today)
  expect_identical(multi$origins@items@values, c("Asia", "Europe", "USA"))
  dates <- tool_arguments(load_fix("dates"), today)
  expect_match(dates$cutoff@description, "to 2026-11-11")
  expect_s3_class(dates$period, "ellmer::TypeArray")
  expect_length(tool_arguments(load_fix("dataset"), today), 0L)
})

test_that("a valid call returns a summary", {
  out <- jsonlite::fromJSON(call_tool(load_fix("numeric"), mock(), list(min_msrp = 30000), today))
  expect_identical(out$status, "success")
  expect_true(nzchar(out$run_id))
})

test_that("invalid model arguments become V-codes, not errors", {
  out <- jsonlite::fromJSON(call_tool(load_fix("numeric"), mock(),
    list(min_msrp = 999999, bogus = 1), today))
  expect_identical(out$status, "error")
  expect_setequal(out$issues$code, c("V003", "V011"))
})

test_that("the summary previews tables and the first ERROR, without HTML", {
  contract <- load_fix("outputs")
  tables <- names(Filter(function(s) identical(s$type, "table"), contract$data$outputs))
  skip_if(length(tables) == 0L)
  result <- list(run_id = "r1", status = "warning",
    log = "NOTE: ok\nERROR: Variable X not found.\nERROR: second",
    outputs = stats::setNames(list(list(columns = list(list(name = "a")),
      rows = lapply(1:30, list), total_rows = 30L)), tables[[1]]),
    metadata = list())
  result$outputs$report <- "<html>never sent</html>"
  out <- summarise_result(contract, result)
  expect_identical(out$error, "ERROR: Variable X not found.")
  expect_length(out$tables[[tables[[1]]]]$rows, 20L)
  expect_false(grepl("<html>", jsonlite::toJSON(out, auto_unbox = TRUE)))
})