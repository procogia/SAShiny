# choices_from caching (spec section 6.4, #130 J3). No SAS: a counting fake engine.

counting_contract <- function(ttl = NULL) {
  dir <- tempfile("sashiny-choices-")
  dir.create(dir)
  writeLines("data _null_; run;", file.path(dir, "program.sas"))
  lines <- c("sashiny: 1", "program: program.sas", "title: Choices", "inputs:", "  make:",
    "    type: choice", "    label: Make",
    "    choices_from: {dataset: sashelp.cars, value_column: make}",
    "outputs:", "  log:", "    type: log")
  if (!is.null(ttl)) lines <- c(lines, "run:", paste0("  choices_ttl_seconds: ", ttl))
  writeLines(lines, file.path(dir, "contract.sashiny.yml"))
  sas_contract(file.path(dir, "contract.sashiny.yml"))
}

# A counting engine (an environment, as real engines are) built on the mock.
counting_engine <- function(fail = FALSE) {
  e <- new.env(parent = emptyenv())
  e$queries <- 0L
  e$fail <- fail
  e$mock <- .sashiny_engine_mock(choices = list(make = c("Acura", "BMW")))
  class(e) <- c("sashiny_counting", "sashiny_engine")
  e
}

local({
  registerS3method("sas_engine_choices", "sashiny_counting", function(engine, contract) {
    engine$queries <- engine$queries + 1L
    if (isTRUE(engine$fail)) stop("library SASHELP is not assigned")
    sas_engine_choices(engine$mock, contract)
  })
  registerS3method("sas_engine_run", "sashiny_counting", function(engine, contract, values,
                                                                   today = Sys.Date(),
                                                                   uploads = NULL, run_id = NULL) {
    if (is.null(contract$cached_choices)) engine$queries <- engine$queries + 1L
    sas_engine_run(engine$mock, contract, values, today = today, uploads = uploads, run_id = run_id)
  })
})

test_that("choices load once for many sessions of one app (spec section 6.4)", {
  skip_if_not_installed("shiny")
  engine <- counting_engine()
  contract <- counting_contract()
  for (i in 1:5) {
    shiny::testServer(sas_program_server, args = list(contract = contract, engine = engine), {
      session$setInputs(make = "BMW", run = 1)
      expect_identical(result()$status, "success")
    })
  }
  # One query for five sessions and five runs.
  expect_identical(engine$queries, 1L)
})

test_that("an expired TTL reloads, and TTL 0 never reuses", {
  engine <- counting_engine()
  contract <- counting_contract(ttl = 60)
  .sashiny_choices(engine, contract)
  .sashiny_choices(engine, contract)
  expect_identical(engine$queries, 1L)
  key <- .sashiny_contract_sha256(contract)
  hit <- get(key, envir = engine$choices_cache)
  hit$at <- hit$at - 61
  assign(key, hit, envir = engine$choices_cache)
  .sashiny_choices(engine, contract)
  expect_identical(engine$queries, 2L)
  never <- counting_engine()
  zero <- counting_contract(ttl = 0)
  .sashiny_choices(never, zero)
  .sashiny_choices(never, zero)
  expect_identical(never$queries, 2L)
})

test_that("a replaced session clears the cache", {
  engine <- counting_engine()
  contract <- counting_contract()
  .sashiny_choices(engine, contract)
  .sashiny_clear_choices(engine)
  expect_null(.sashiny_cached_choices(engine, contract))
})

test_that("a load failure shows in the status card and is not cached (#68)", {
  skip_if_not_installed("shiny")
  engine <- counting_engine(fail = TRUE)
  contract <- counting_contract()
  shiny::testServer(sas_program_server, args = list(contract = contract, engine = engine), {
    expect_match(output$status, "could not read choices: library SASHELP is not assigned",
      fixed = TRUE)
  })
  expect_null(.sashiny_cached_choices(engine, contract))
})

test_that("a run before choices are loaded still validates against them", {
  engine <- counting_engine()
  contract <- counting_contract()
  bad <- sas_engine_run(engine, contract, list(make = "Saab"), today = .sashiny_today)
  expect_identical(bad$status, "error")
  expect_identical(bad$metadata$issues[[1]]$input, "make")
  ok <- sas_engine_run(engine, contract, list(make = "BMW"), today = .sashiny_today)
  expect_identical(ok$status, "success")
})

test_that("the async load resolves and fills the cache", {
  skip_if_not_installed("promises")
  skip_if_not_installed("later")
  engine <- counting_engine()
  contract <- counting_contract()
  value <- NULL
  promises::then(.sashiny_choices_async(engine, contract), function(v) value <<- v)
  for (i in 1:20) later::run_now(0.01)
  expect_identical(vapply(value$make, function(c) c$value, ""), c("Acura", "BMW"))
  expect_false(is.null(.sashiny_cached_choices(engine, contract)))
})
