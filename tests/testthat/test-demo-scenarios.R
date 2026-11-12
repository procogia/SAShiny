# Offline checks of the demo scenarios (examples/demo-scenarios.yml), shared
# with Python/tests/test_demo_scenarios.py.

test_that("scenario ids are unique and each track has a primary", {
  skip_if_no_demo_scenarios()
  scenarios <- demo_scenarios()
  ids <- vapply(scenarios, function(s) s$id, "")
  expect_false(anyDuplicated(ids) > 0)
  paths <- vapply(scenarios, function(s) s$contract_path, "")
  primary <- vapply(scenarios, function(s) s$primary, logical(1))
  expect_setequal(paths[primary], unique(paths))
})

test_that("every scenario's values are valid for its contract", {
  skip_if_no_demo_scenarios()
  for (s in demo_scenarios()) {
    contract <- sas_contract(s$contract_path)
    expect_length(sas_validate(contract, .demo_today), 0)
    res <- sas_render_values(contract$data, s$values, .demo_today, uploads = s$uploads)
    expect_identical(res$issues, list(), info = s$id)
    expect_true(length(res$macros) > 0, info = s$id)
    expected_ids <- c(names(s$expect$tables), names(s$expect$plots))
    expect_true(all(expected_ids %in% names(contract$data$outputs)), info = s$id)
  }
})

test_that("primary scenarios equal the UI defaults", {
  skip_if_no_demo_scenarios()
  for (s in Filter(function(s) s$primary, demo_scenarios())) {
    expect_identical(demo_default_problems(s, sas_contract(s$contract_path)), character(0),
      info = s$id
    )
  }
})

# ---------------------------------------------------------------- checker self-test

demo_good_result <- function(contract) {
  outputs <- lapply(names(contract$data$outputs), function(oid) {
    spec <- contract$data$outputs[[oid]]
    switch(spec$type,
      table = list(
        columns = list(list(name = "a", type = "character", label = "", format = "")),
        rows = list(list("x")), total_rows = 1L, truncated = FALSE, formatted = TRUE
      ),
      plot = list(list(mime = "image/png", data = "QQ==")),
      html = "<html><body>ok</body></html>",
      log = list(list(level = "note", text = "NOTE: ok")),
      download = {
        data <- if (identical(spec$format, "csv")) {
          charToRaw("a,b\n1,2\n")
        } else {
                magic <- .demo_magic[[spec$format]]
                magic <- if (is.list(magic)) magic[[1]] else magic
                c(magic, charToRaw("rest"))
              }
              list(
                filename = paste0(spec$filename %||% oid, ".", spec$format), mime = "x",
                data = openssl::base64_encode(data)
              )
            }
    )
  })
  sashiny_result("r", "success", outputs = stats::setNames(outputs, names(contract$data$outputs)))
}

test_that("the checker accepts a complete result", {
  skip_if_no_demo_scenarios()
  for (s in Filter(function(s) s$primary, demo_scenarios())) {
    contract <- sas_contract(s$contract_path)
    expect_identical(demo_check_result(demo_good_result(contract), contract, s), character(0),
      info = s$id
    )
  }
})

test_that("the checker accepts a v8 XPT download", {
  skip_if_no_demo_scenarios()
  s <- demo_scenario("pharma")
  contract <- sas_contract(s$contract_path)
  result <- demo_good_result(contract)
  # Replace the pharma ae_xpt download with a v8 header (long member name).
  v8 <- charToRaw("HEADER RECORD*******LIBV8   HEADER RECORD")
  result$outputs$ae_xpt <- list(
    filename = "ae_soc_pt.xpt", mime = "application/x-sas-transport",
    data = openssl::base64_encode(c(v8, charToRaw("rest")))
  )
  problems <- demo_check_result(result, contract, s)
  expect_false(any(grepl("ae_xpt", problems, fixed = TRUE)), info = paste(problems, collapse = "\n"))
})

test_that("the checker reports every problem", {
  skip_if_no_demo_scenarios()
  s <- demo_scenario("general")
  contract <- sas_contract(s$contract_path)
  result <- demo_good_result(contract)
  result$status <- "warning"
  result$metadata$collect_errors <- list("report_pdf: download failed")
  result$outputs$stats$rows <- list()
  result$outputs$price_vs_mpg <- list()
  result$outputs$report <- "plain text"
  result$outputs$log <- list(list(level = "error", text = "ERROR: boom"))
  result$outputs$report_pdf <- list(
    filename = "cars_report.pdf", mime = "application/pdf",
    data = openssl::base64_encode(charToRaw("not a pdf"))
  )
  result$outputs$stats_csv <- list(error = "dataset WORK.CARS_STATS not found")
  result$outputs$price_by_type <- NULL
  problems <- paste(demo_check_result(result, contract, s), collapse = "\n")
  for (expected in c(
    "status 'warning'", "collect error: report_pdf", "stats: 0 rows",
    "price_vs_mpg: 0 graphs", "price_by_type: missing", "report: not an HTML document",
    "SAS log error: ERROR: boom", "report_pdf: not a valid .pdf",
    "stats_csv: dataset WORK.CARS_STATS not found"
  )) {
    expect_true(grepl(expected, problems, fixed = TRUE), info = expected)
  }
})

test_that("drift from the contract defaults is detected", {
  skip_if_no_demo_scenarios()
  s <- demo_scenario("general-msrp-40000")
  expect_identical(
    demo_default_problems(s, sas_contract(s$contract_path)),
    "min_msrp: scenario value 40000L != contract default 20000L"
  )
})

# ---------------------------------------------------------------- committed recordings

test_that("committed recordings replay and are demo-ready", {
  skip_if_no_demo_scenarios()
  engine <- sas_engine_mock(file.path(.demo_examples(), "recordings"))
  missing <- character(0)
  for (s in demo_scenarios()) {
    contract <- sas_contract(s$contract_path)
    result <- sas_engine_run(engine, contract, s$values, .demo_today, uploads = s$uploads)
    if (identical(result$metadata$recording, "missing")) {
      if (identical(Sys.getenv("SASHINY_REQUIRE_RECORDINGS"), "1")) {
        fail(paste("no recording for", s$id, "in examples/recordings"))
      }
      missing <- c(missing, s$id)
      next
    }
    expect_identical(demo_check_result(result, contract, s), character(0), info = s$id)
  }
  if (length(missing) > 0L) {
    skip(paste("no recording for", paste(missing, collapse = ", "), "in examples/recordings"))
  }
})
