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
  engine <- .sashiny_engine_mock()
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
  engine <- .sashiny_engine_mock()
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
  engine <- .sashiny_engine_mock()
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

test_that("status text reports issues and errors", {
  r <- .sashiny_result("run-1", "success", metadata = list())
  expect_identical(.sashiny_status_text(r), "status: success\nrun_id: run-1")
  r$metadata <- list(
    sas_version = "9.04.01M8",
    issues = list(list(code = "V002", input = "n")), notice = "fallback",
    engine_error = "boom", collect_errors = list("t: gone")
  )
  text <- .sashiny_status_text(r)
  parts <- c(
    "SAS: 9.04.01M8", "V002 n", "fallback", "engine error: boom", "t: gone"
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
      prefix <- if (is_download) "mod-dl_btn_" else "mod-out_"
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
  live <- test_saspy_engine(list(), session_factory = function() fake_session())
  result <- sas_engine_run(live, contract, list(min_age = 18), uploads = list(adsl = TRUE))
  test_save_recording(rec, contract, result,
    files = list(adsl = file.path(contract$base_dir, "adsl.csv"))
  )
  engine <- .sashiny_engine_mock(rec)
  shiny::testServer(
    sas_program_server,
    args = list(contract = contract, engine = engine),
    {
      session$setInputs(min_age = 18, adsl__sample = TRUE, run = 1)
      expect_match(output$status, "status: success", fixed = TRUE)
      expect_match(output$out_stats$html, "Age (y)", fixed = TRUE)
      expect_match(output$out_missing$html, "dataset WORK.NOPE not found", fixed = TRUE)
      expect_match(output$out_graphs$html, "data:image/png;base64", fixed = TRUE)
      expect_false(grepl("SASHINY", output$out_log$html, fixed = TRUE))
    }
  )
})

test_that("the module shows a choices_from error before the first run", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "choice", "contract.sashiny.yml"))
  engine <- structure(list(), class = c("sashiny_broken_choices", "sashiny_engine"))
  registerS3method("sas_engine_choices", "sashiny_broken_choices",
    function(engine, contract) stop("SAS unreachable"),
    envir = asNamespace("SAShiny")
  )
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      # No Run click yet: the status card must already show the choice error.
      expect_match(output$status, "could not read choices", fixed = TRUE)
      expect_match(output$status, "SAS unreachable", fixed = TRUE)
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
    .sashiny_result("r1", "success", outputs = list(first = value, second = value, log = list()))
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

  test_that("upload limit is raised to the largest max_size_mb and restored", {
    skip_on_cran()
    skip_if_not_installed("shiny")
    prev <- getOption("shiny.maxRequestSize")
    on.exit(options(shiny.maxRequestSize = prev), add = TRUE)
    inputs <- list(
      a = list(type = "dataset", max_size_mb = 10),
      b = list(type = "dataset", max_size_mb = 50),
      c = list(type = "numeric")
    )
    .sashiny_set_upload_limit(inputs)
    expect_identical(getOption("shiny.maxRequestSize"), 50 * 1024 * 1024)
    .sashiny_restore_upload_limit()
    expect_identical(getOption("shiny.maxRequestSize"), prev)
  })

  test_that("upload limit defaults to 50 MB when undeclared", {
    skip_on_cran()
    skip_if_not_installed("shiny")
    prev <- getOption("shiny.maxRequestSize")
    on.exit(options(shiny.maxRequestSize = prev), add = TRUE)
    .sashiny_set_upload_limit(list(a = list(type = "dataset")))
    expect_identical(getOption("shiny.maxRequestSize"), 50 * 1024 * 1024)
    .sashiny_restore_upload_limit()
  })

# ---------------------------------------------------------------- paired outputs (section 8.6)

paired_contract <- function() {
  sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "paired_outputs",
                         "contract.sashiny.yml"))
}

paired_value <- function(x = "x", y = "y") {
  chart <- list(
    columns = list(
      list(name = x, type = "character", label = "", format = ""),
      list(name = y, type = "numeric", label = "", format = "")
    ),
    rows = list(list("a", 2), list("b", 4)), total_rows = 2L, truncated = FALSE, formatted = FALSE
  )
  list(sas = list(list(mime = "image/png", data = "QUJD")), sashiny = chart)
}

paired_spec <- function() {
  list(type = "chart", from = "work.t", sas_plot = 1L,
       spec = list(kind = "bar", x = "x", y = "y"))
}

test_that("a paired tag renders both views and the toggle", {
  skip_if_not_installed("shiny")
  skip_if_not_installed("htmltools")
  html <- as.character(.sashiny_paired_tag(paired_value(), paired_spec(), "p", "mod-views"))
  expect_match(html, "data-sashiny-paired", fixed = TRUE)
  expect_match(html, "data-sashiny-default=\"sashiny\"", fixed = TRUE)
  expect_match(html, "data-sashiny-group=\"mod-views\"", fixed = TRUE)
  expect_equal(lengths(regmatches(html, gregexpr("data-sashiny-pane=", html, fixed = TRUE))), 2L)
  expect_match(html, "data:image/png;base64,QUJD", fixed = TRUE)
  expect_match(html, "SAS graph", fixed = TRUE)
  expect_match(html, "SAShiny chart", fixed = TRUE)
  # Only the default view is visible.
  sas_pane <- sub(".*(data-sashiny-pane=\"sas\"[^>]*>).*", "\\1", html)
  expect_match(sas_pane, "hidden", fixed = TRUE)
  expect_match(as.character(.sashiny_paired_tag(
    paired_value(), paired_spec(), "p", "g", view = "sas"
  )), "data-sashiny-view=\"sas\"", fixed = TRUE)
})

test_that("a paired tag without the toggle shows only the default view", {
  skip_if_not_installed("shiny")
  chart_only <- as.character(.sashiny_paired_tag(
    paired_value(), paired_spec(), "p", "g", toggle = FALSE
  ))
  expect_false(grepl("data-sashiny-paired", chart_only, fixed = TRUE))
  expect_false(grepl("QUJD", chart_only, fixed = TRUE))
  sas_only <- as.character(.sashiny_paired_tag(
    paired_value(), paired_spec(), "p", "g", toggle = FALSE, view = "sas"
  ))
  expect_match(sas_only, "QUJD", fixed = TRUE)
  expect_false(grepl("data-sashiny-paired", sas_only, fixed = TRUE))
})

test_that("a failed part is reported without hiding the other part", {
  skip_if_not_installed("shiny")
  skip_if_not_installed("ggplot2") # the chart part renders as an <img>
  value <- paired_value()
  value$sas <- list(error = "select=3 but the run produced 2 graph(s)")
  html <- as.character(.sashiny_paired_tag(value, paired_spec(), "p", "g"))
  expect_match(html, "select=3 but the run produced 2 graph(s)", fixed = TRUE)
  expect_equal(lengths(regmatches(html, gregexpr("<img", html, fixed = TRUE))), 1L)
})

test_that("paired helpers recognise both pairing forms", {
  plot <- list(type = "plot", select = 2L, chart = list(from = "work.m", max_rows = 5L, spec = list()))
  expect_identical(
    .sashiny_paired_chart_spec(plot),
    list(type = "chart", from = "work.m", max_rows = 5L, spec = list())
  )
  expect_identical(.sashiny_paired_parts(plot)$select, 2L)
  expect_identical(.sashiny_paired_parts(paired_spec())$select, 1L)
  expect_true(.sashiny_is_paired(plot))
  expect_true(.sashiny_is_paired(paired_spec()))
  expect_false(.sashiny_is_paired(list(type = "plot", select = 1L)))
  expect_false(.sashiny_is_paired(list(type = "chart", from = "work.t")))
})

test_that("chart_view defaults and validation follow spec section 8.6", {
  contract <- paired_contract()
  expect_identical(.sashiny_chart_views(contract, "sashiny"),
    c(scatter = "sashiny", bars = "sashiny"))
  expect_identical(.sashiny_chart_views(contract, "sas"), c(scatter = "sas", bars = "sas"))
  expect_identical(.sashiny_chart_views(contract, list(bars = "sas")),
    c(scatter = "sashiny", bars = "sas"))
  expect_error(.sashiny_chart_views(contract, "both"), "chart_view")
  expect_error(.sashiny_chart_views(contract, list(bars = "x")), "chart_view")
  expect_error(.sashiny_chart_views(contract, list(nope = "sas")), "not paired")
  expect_error(.sashiny_chart_views(contract, 3), "chart_view")
})

test_that("the module UI has the module toggle only for paired contracts", {
  skip_if_not_installed("shiny")
  expect_match(as.character(sas_program_ui("m", paired_contract())), "m-out__view", fixed = TRUE)
  plain <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "outputs",
                                  "contract.sashiny.yml"))
  expect_false(grepl("out__view", as.character(sas_program_ui("m", plain)), fixed = TRUE))
})

paired_engine <- function() {
  engine <- structure(list(), class = c("sashiny_paired_engine", "sashiny_engine"))
  registerS3method("sas_engine_run", "sashiny_paired_engine", function(engine, contract, values, ...) {
    .sashiny_result("r1", "success",
      outputs = list(
        scatter = paired_value("height", "weight"), bars = paired_value("sex", "weight")
      )
    )
  }, envir = asNamespace("SAShiny"))
  engine
}

test_that("the module renders paired cards, the module toggle and honours the settings", {
  skip_if_not_installed("ggplot2") # the default chart backend
  skip_on_cran()
  skip_if_not_installed("shiny")
  skip_if_not_installed("htmltools")
  contract <- paired_contract()
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = paired_engine()), {
      session$setInputs(run = 1)
      expect_match(output$out_scatter$html, "data-sashiny-default=\"sashiny\"", fixed = TRUE)
      expect_match(output$out_scatter$html, "data:image/png;base64,QUJD", fixed = TRUE)
      # The SAShiny chart is drawn too: a second image next to the SAS graph.
      expect_equal(lengths(regmatches(output$out_scatter$html,
        gregexpr("<img", output$out_scatter$html, fixed = TRUE))), 2L)
      expect_match(output$out__view$html, "SAS graphs", fixed = TRUE)
      expect_match(output$out__view$html, "data-sashiny-default=\"sashiny\"", fixed = TRUE)
    }
  )
  shiny::testServer(
    sas_program_server,
    args = list(contract = contract, engine = paired_engine(), chart_view = list(bars = "sas")), {
      session$setInputs(run = 1)
      expect_match(output$out_bars$html, "data-sashiny-default=\"sas\"", fixed = TRUE)
      expect_false(grepl("data-sashiny-default", output$out__view$html, fixed = TRUE))
    }
  )
  shiny::testServer(
    sas_program_server,
    args = list(contract = contract, engine = paired_engine(),
                chart_view = "sas", chart_toggle = FALSE), {
      session$setInputs(run = 1)
      expect_false(grepl("data-sashiny-paired", output$out_scatter$html, fixed = TRUE))
      expect_match(output$out_scatter$html, "QUJD", fixed = TRUE)
      expect_false(nzchar(output$out__view$html %||% ""))
    }
  )
})

test_that("sas_app passes chart settings to every module and validates them", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  skip_if_not_installed("htmltools")
  paired <- paired_contract()
  engine <- .sashiny_engine_mock()
  expect_s3_class(sas_app(list(paired), engine, chart_view = "sas", chart_toggle = FALSE),
    "shiny.appobj")
  expect_s3_class(sas_app(list(paired), engine, chart_view = list(bars = "sas")), "shiny.appobj")
  expect_error(sas_app(list(paired), engine, chart_view = list(missing = "sas")), "not paired")
})
test_that("the download button is namespaced and the placeholder has no id", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  dir <- tempfile("sashiny-dl-")
  dir.create(dir)
  writeLines("data a; x = 1; run;", file.path(dir, "p.sas"))
  writeLines(c(
    "sashiny: 1", "program: p.sas", "outputs:",
    "  rep:", "    type: download", "    format: csv", "    from: work.a",
    "  log:", "    type: log"
  ), file.path(dir, "p.sashiny.yml"))
  contract <- sas_contract(file.path(dir, "p.sashiny.yml"))
  engine <- structure(list(), class = c("sashiny_dl_engine", "sashiny_engine"))
  registerS3method("sas_engine_run", "sashiny_dl_engine", function(engine, contract, values, ...) {
    file <- list(filename = "rep.csv", data = openssl::base64_encode(charToRaw("x\n1\n")))
    .sashiny_result("r1", "success", outputs = list(rep = file, log = list()))
  }, envir = asNamespace("SAShiny"))
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      # Before a run: a disabled placeholder that does not reuse the output id.
      expect_match(output$dl_btn_rep$html, "disabled", fixed = TRUE)
      expect_false(grepl("id=", output$dl_btn_rep$html, fixed = TRUE))
      session$setInputs(run = 1)
      # After a run: the real button carries the module-namespaced handler id.
      expect_match(output$dl_btn_rep$html, paste0('id="', session$ns("dl_rep"), '"'), fixed = TRUE)
    }
  )
})

test_that("the Run button is a task button with the contract's run label", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  skip_if_not(.sashiny_has_task_button(), "bslib >= 0.7.0 not installed")
  contract <- fake_contract()
  contract$data$ui$run_label <- "Build tables"
  html <- as.character(sas_program_ui("mod", contract, today = as.Date("2026-11-11")))
  expect_match(html, "bslib-task-button", fixed = TRUE)
  expect_match(html, "id=\"mod-run\"", fixed = TRUE)
  expect_match(html, "Build tables", fixed = TRUE)
  expect_match(html, "Running...", fixed = TRUE)
})

test_that("the Run button falls back to an action button without bslib task buttons", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  local_mocked_bindings(.sashiny_has_task_button = function() FALSE)
  html <- as.character(sas_program_ui("mod", fake_contract(), today = as.Date("2026-11-11")))
  expect_false(grepl("bslib-task-button", html, fixed = TRUE))
  expect_match(html, "action-button", fixed = TRUE)
  expect_match(html, "id=\"mod-run\"", fixed = TRUE)
})

test_that("a click during a run is ignored and the Run card shows running...", {
  skip_on_cran()
  skip_if_not_installed("shiny")
  skip_if_not_installed("promises")
  skip_if_not_installed("later")
  skip_if_not_installed("callr")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  engine <- .sashiny_engine_mock()
  done <- sas_engine_run(engine, contract, list())
  # Pretend the app is running so the module uses its ExtendedTask, and hold
  # each background run open until the test resolves it.
  started <- 0L
  resolvers <- list()
  local_mocked_bindings(isRunning = function() TRUE, .package = "shiny")
  local_mocked_bindings(
    .sashiny_portable_engine = function(engine) engine,
    .sashiny_run_bg_promise = function(...) {
      started <<- started + 1L
      promises::promise(function(resolve, reject) resolvers[[length(resolvers) + 1L]] <<- resolve)
    }
  )
  shiny::testServer(
    sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(run = 1)
      expect_identical(started, 1L)
      expect_identical(output$status, "running...")
      session$setInputs(run = 2)
      session$setInputs(run = 3)
      resolvers[[1]](done)
      for (i in 1:20) later::run_now(0.01)
      session$flushReact()
      # The two extra clicks were ignored, not queued behind the first run.
      expect_identical(started, 1L)
      expect_identical(result()$status, "success")
      expect_match(output$status, "status: success", fixed = TRUE)
    }
  )
})
