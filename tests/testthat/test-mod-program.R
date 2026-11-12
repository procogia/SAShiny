# Tests for the Shiny modules (issue #8).

test_that("sas_program_ui returns a tagList", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  ui <- sas_program_ui("mod", contract)
  expect_s3_class(ui, "shiny.tag.list")
})

test_that("sas_program_server runs a contract and returns reactives", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(run = 1)
      expect_identical(result()$status, "success")
      expect_identical(result()$log, "")
    }
  )
})

test_that("sas_program_server collects inputs from a numeric contract", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(min_msrp = 20000, ratio = 0.5, big = 1)
      session$setInputs(run = 1)
      expect_identical(result()$status, "success")
    }
  )
})

test_that("sas_program_server reports invalid values", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  engine <- sas_engine_mock()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(min_msrp = "not-a-number", ratio = 0.5, big = 1)
      session$setInputs(run = 1)
      expect_identical(result()$status, "error")
    }
  )
})
test_that("Shiny values convert to the contract's JSON form", {
  dir <- tempfile("sashiny-vals-")
  dir.create(dir)
  contract <- structure(list(
    data = list(sashiny = 1L, program = "p.sas", outputs = list(), inputs = list(
      n = list(type = "numeric"), n2 = list(type = "numeric"),
      c = list(type = "choice", choices = list("a")),
      m = list(type = "multichoice", choices = list("a", "b")),
      d = list(type = "date"), r = list(type = "daterange"), r2 = list(type = "daterange"),
      f = list(type = "dataset", target = "work.f"),
      s = list(type = "dataset", target = "work.s", sample = "s.csv"),
      t = list(type = "text")
    )),
    base_dir = dir
  ), class = "sashiny_contract")
  shiny_inputs <- list(
    n = 3, n2 = NA, c = "", m = c("a", "b"), d = as.Date("2026-01-02"),
    r = as.Date(c("2026-01-01", "2026-02-01")), r2 = as.Date(c(NA, NA)),
    f = data.frame(name = "real.csv", size = 1, type = "text/csv", datapath = "/tmp/0.csv"),
    s__sample = TRUE, t = " hi "
  )
  converted <- .sashiny_shiny_values(contract, function(iid) shiny_inputs[[iid]])
  expect_identical(converted$values, list(
    n = 3, m = list("a", "b"), d = "2026-01-02", r = list("2026-01-01", "2026-02-01"), t = " hi "
  ))
  expect_identical(converted$uploads$f, .sashiny_upload_file("/tmp/0.csv", "real.csv"))
  expect_true(converted$uploads$s)
})

test_that("status text reports recordings, issues and errors", {
  r <- sashiny_result("run-1", "success", metadata = list())
  expect_identical(.sashiny_status_text(r), "status: success\nrun_id: run-1")
  r$metadata <- list(
    sas_version = "9.04.01M8", recording = "missing",
    issues = list(list(code = "V002", input = "n")), notice = "fallback",
    engine_error = "boom", collect_errors = list("t: gone")
  )
  text <- .sashiny_status_text(r)
  parts <- c(
    "SAS: 9.04.01M8", "no recording", "V002 n", "fallback", "engine error: boom", "t: gone"
  )
  for (part in parts) {
    expect_match(text, part, fixed = TRUE)
  }
})

test_that("output values render as HTML", {
  skip_if_not_installed("shiny")
  table <- list(
    columns = list(
      list(name = "n", type = "numeric", label = "Count", format = ""),
      list(name = "s", type = "character", label = "", format = "")
    ),
    rows = list(list(1, "<b>"), list(NULL, "x")),
    total_rows = 9L, truncated = TRUE, formatted = FALSE
  )
  html <- as.character(.sashiny_output_tag("table", table))
  expect_match(html, "Count", fixed = TRUE)
  expect_match(html, "&lt;b&gt;", fixed = TRUE)
  expect_match(html, "Showing 2 of 9 rows.", fixed = TRUE)
  expect_match(as.character(.sashiny_plot_tag(list())), "No graphs")
  img <- as.character(.sashiny_plot_tag(list(list(mime = "image/png", data = "QUJD"))))
  expect_match(img, "data:image/png;base64,QUJD", fixed = TRUE)
  frame <- as.character(.sashiny_html_tag("<p>hi</p>"))
  expect_match(frame, "sandbox=\"\"", fixed = TRUE)
  expect_match(as.character(.sashiny_html_tag("")), "No HTML")
  log <- as.character(.sashiny_log_tag(list(list(level = "error", text = "ERROR: x"))))
  expect_match(log, "#b42318", fixed = TRUE)
  expect_match(as.character(.sashiny_output_tag("table", list(error = "gone"))), "gone")
})

test_that("the module UI has one card per output and uses contract defaults", {
  skip_if_not_installed("shiny")
  contract <- fake_contract()
  html <- as.character(sas_program_ui("mod", contract, today = as.Date("2026-11-11")))
  for (oid in names(contract$data$outputs)) {
    is_download <- identical(contract$data$outputs[[oid]]$type, "download")
    prefix <- if (is_download) "mod-dl_" else "mod-out_"
    expect_match(html, paste0(prefix, oid), fixed = TRUE)
  }
  expect_match(html, "Use the sample file", fixed = TRUE)
  expect_match(html, "value=\"18\"", fixed = TRUE)
})

test_that("the module replays a recording into its output cards", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  rec <- tempfile("sashiny-rec-")
  contract <- fake_contract()
  live <- sas_engine_saspy(list(), session_factory = function() fake_session(), record_to = rec)
  sas_engine_run(live, contract, list(min_age = 18), uploads = list(adsl = TRUE))
  engine <- sas_engine_mock(rec)
  shiny::testServer(
    sas_program_server,
    args = list(contract = contract, engine = engine),
    {
      session$setInputs(min_age = 18, adsl__sample = TRUE, run = 1)
      expect_match(output$status, "replayed recording", fixed = TRUE)
      expect_match(output$out_stats$html, "Age (y)", fixed = TRUE)
      expect_match(output$out_missing$html, "dataset WORK.NOPE not found", fixed = TRUE)
      expect_match(output$out_graphs$html, "data:image/png;base64", fixed = TRUE)
      expect_false(grepl("SASHINY", output$out_log$html, fixed = TRUE))
      session$setInputs(min_age = 99, run = 2)
      expect_match(output$status, "no recording matches", fixed = TRUE)
    }
  )
})

test_that("each chart output gets its own render callback", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  dir <- tempfile("sashiny-render-")
  dir.create(dir)
  writeLines("data a; x = 1; run;", file.path(dir, "p.sas"))
  writeLines(c(
    "sashiny: 1", "program: p.sas", "outputs:",
    "  first:", "    type: chart", "    from: work.a",
    "  second:", "    type: chart", "    from: work.a",
    "  log:", "    type: log"
  ), file.path(dir, "p.sashiny.yml"))
  contract <- sas_contract(file.path(dir, "p.sashiny.yml"))
  value <- list(columns = list(list(name = "x", type = "numeric", label = "", format = "")),
                rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE)
  engine <- structure(list(), class = c("sashiny_test_engine", "sashiny_engine"))
  registerS3method("sas_engine_run", "sashiny_test_engine", function(engine, contract, values, ...) {
    sashiny_result("r1", "success", outputs = list(first = value, second = value, log = list()))
  }, envir = asNamespace("SAShiny"))
  # Each callback names itself in its error, which the chart card shows.
  render <- list(
    first = function(value, spec) stop("first callback"),
    second = function(value, spec) stop("second callback")
  )
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine, render = render), {
      session$setInputs(run = 1)
      expect_match(output$out_first$html, "first callback", fixed = TRUE)
      expect_match(output$out_second$html, "second callback", fixed = TRUE)
    }
  )
})
