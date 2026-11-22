# Replay engine, registered engines and recordings (spec section 6.6, 8.3).

replay_dir <- function() file.path(dirname(.sashiny_fixtures()), "fixtures", "replay")

# The replay fixtures are only in the source repository: their paths are too
# long for a CRAN tarball, like the deploy fixtures.
skip_without_replay_fixtures <- function() {
  skip_if_not(dir.exists(replay_dir()), "replay fixtures are only in the source repository")
}

replay_cases <- function() {
  jsonlite::fromJSON(file.path(replay_dir(), "cases.json"), simplifyVector = FALSE)
}

# A copy of the replay fixture contract and program in a temporary folder.
copy_replay_contract <- function() {
  dir <- tempfile("replay")
  dir.create(dir)
  file.copy(file.path(replay_dir(), c("replay.sashiny.yml", "replay.sas")), dir)
  dir
}

# A stand-in for an engine that runs on licensed SAS (the tests have no SAS).
run_test_batch <- function(engine, contract, values, today = Sys.Date(),
                                              uploads = NULL, run_id = NULL) {
  rendered <- sas_render_values(contract$data, values, today)
  sas_engine_result(contract, "success",
    outputs = list(log = list(list(level = "note", text = "NOTE: batch"))),
    log = "NOTE: SASHINY-BEGIN-PROGRAM\nNOTE: batch\nNOTE: SASHINY-END-PROGRAM\n",
    macros = rendered$macros, sas_version = "9.04.01M0P061913", engine = "test-batch",
    run_id = run_id
  )
}
registerS3method("sas_engine_run", "test_batch_engine", run_test_batch,
  envir = asNamespace("SAShiny")
)
test_batch_engine <- function() structure(list(), class = "test_batch_engine")

test_that("the replay engine matches every shared fixture case (spec 6.6 (a))", {
  skip_without_replay_fixtures()
  spec <- replay_cases()
  contract <- sas_contract(file.path(replay_dir(), spec$contract))
  engine <- sas_replay(file.path(replay_dir(), "recordings"))
  today <- as.Date(spec$today)
  for (case in spec$cases) {
    # Outside the test suite, so the public guard must accept the engine.
    result <- outside_tests(sas_run(contract, engine, case$values, today = today))
    exp <- case$expected
    label <- case$name
    expect_identical(result$status, exp$status, label = label)
    expect_identical(result$metadata$recording, exp$recording, label = label)
    expect_identical(result$metadata$engine_error, exp$engine_error, label = label)
    expect_identical(result$metadata$notice, exp$notice, label = label)
    if (!is.null(exp$sas_version)) {
      expect_identical(result$metadata$sas_version, exp$sas_version, label = label)
      expect_identical(result$metadata$recorded_at, exp$recorded_at, label = label)
      expect_identical(result$metadata$engine, "replay", label = label)
      expect_identical(result$log, exp$log, label = label)
      expect_identical(result$outputs, exp$outputs, label = label)
    }
    if (!is.null(exp$issues)) {
      got <- lapply(result$metadata$issues, function(i) list(code = i$code, input = i$input))
      expect_identical(got, exp$issues, label = label)
    }
    if (identical(exp$recording, "refused") || identical(exp$recording, "missing")) {
      expect_identical(result$outputs, list(), label = label)
      expect_identical(result$log, "", label = label)
    }
  }
})

test_that("a replayed result is labelled in the module's status text", {
  skip_without_replay_fixtures()
  contract <- sas_contract(file.path(replay_dir(), "replay.sashiny.yml"))
  engine <- sas_replay(file.path(replay_dir(), "recordings"))
  result <- sas_run(contract, engine, list(case = 1))
  text <- .sashiny_status_text(result)
  expect_match(text, "Replayed from 9.04.01M0P061913, recorded 2015-07-30T12:00:00Z.", fixed = TRUE)
  refused <- .sashiny_status_text(sas_run(contract, engine, list(case = 2)))
  expect_match(refused, "engine error: recording not replayed: it has no SAS version", fixed = TRUE)
})

test_that("the module server accepts the replay engine outside the test suite", {
  skip_without_replay_fixtures()
  skip_if_not_installed("shiny")
  contract <- sas_contract(file.path(replay_dir(), "replay.sashiny.yml"))
  engine <- sas_replay(file.path(replay_dir(), "recordings"))
  outside_tests(shiny::testServer(
    sas_program_server,
    args = list(contract = contract, engine = engine), {
      session$setInputs(case = 1, run = 1)
      expect_identical(result()$metadata$recording, "replayed")
      expect_match(output$status, "Replayed from 9.04.01M0P061913", fixed = TRUE)
    }
  ))
})

test_that("a replay refuses a recording made from a changed program", {
  skip_without_replay_fixtures()
  dir <- copy_replay_contract()
  cat("/* changed */\n", file = file.path(dir, "replay.sas"), append = TRUE)
  contract <- sas_contract(file.path(dir, "replay.sashiny.yml"))
  result <- sas_run(contract, sas_replay(file.path(replay_dir(), "recordings")), list(case = 1))
  expect_identical(result$status, "error")
  expect_identical(result$metadata$recording, "refused")
  expect_identical(
    result$metadata$engine_error,
    "recording not replayed: it was made from a different version of the program"
  )
})

test_that("sas_replay() validates its argument and prints", {
  expect_error(sas_replay(NULL), class = "sashiny_error_engine")
  expect_error(sas_replay(""), class = "sashiny_error_engine")
  expect_output(print(sas_replay("recs")), "replay engine")
})

test_that("unregistered engine classes are rejected outside the test suite", {
  skip_without_replay_fixtures()
  contract <- sas_contract(file.path(replay_dir(), "replay.sashiny.yml"))
  outside_tests({
    expect_error(sas_run(contract, test_batch_engine()), class = "sashiny_error_engine")
    expect_error(sas_pool(test_batch_engine()), "sas_register_engine")
  })
})

test_that("a registered engine is accepted by sas_run, pools and the module", {
  skip_without_replay_fixtures()
  skip_if_not_installed("shiny")
  on.exit(sas_unregister_engine("test_batch_engine"), add = TRUE)
  sas_register_engine("test_batch_engine",
    license_ack = TRUE,
    description = "test stand-in for SAS 9.4 batch"
  )
  expect_identical(
    sas_registered_engines()[["test_batch_engine"]], "test stand-in for SAS 9.4 batch"
  )
  contract <- sas_contract(file.path(replay_dir(), "replay.sashiny.yml"))
  outside_tests({
    result <- sas_run(contract, test_batch_engine(), list(case = 3))
    expect_identical(result$status, "success")
    expect_identical(result$metadata$engine, "test-batch")
    expect_identical(result$metadata$macros, list(CASE = "3"))
    expect_identical(
      result$metadata$engine_version, as.character(utils::packageVersion("SAShiny"))
    )
    expect_s3_class(sas_pool(test_batch_engine()), "sashiny_pool")
    shiny::testServer(
      sas_program_server,
      args = list(contract = contract, engine = test_batch_engine()), {
        session$setInputs(case = 2, run = 1)
        expect_identical(result()$metadata$engine, "test-batch")
      }
    )
  })
  sas_unregister_engine("test_batch_engine")
  expect_false("test_batch_engine" %in% names(sas_registered_engines()))
  outside_tests(expect_error(sas_run(contract, test_batch_engine()), "sas_register_engine"))
})

test_that("registration needs an explicit licence acknowledgement and a description", {
  withr::local_options(SAShiny.license_ack = TRUE)
  withr::local_envvar(SASHINY_LICENSE_ACK = "true")
  expect_error(sas_register_engine("test_batch_engine", description = "x"),
    class = "sashiny_error_license"
  )
  expect_error(sas_register_engine("test_batch_engine", license_ack = "yes", description = "x"),
    "SAS licence not acknowledged"
  )
  expect_error(sas_register_engine("test_batch_engine", license_ack = TRUE),
    "description"
  )
  expect_error(sas_register_engine("test_batch_engine", license_ack = TRUE, description = "  "),
    "description"
  )
  expect_error(sas_register_engine("sashiny_engine_mock", license_ack = TRUE, description = "x"),
    "SAShiny's own"
  )
  expect_error(sas_register_engine("no_such_engine", license_ack = TRUE, description = "x"),
    "no sas_engine_run"
  )
  expect_error(sas_register_engine(c("a", "b"), license_ack = TRUE, description = "x"),
    class = "sashiny_error_engine"
  )
  expect_false("test_batch_engine" %in% names(sas_registered_engines()))
})

test_that("sas_engine_result() builds the run metadata of section 8.4", {
  skip_without_replay_fixtures()
  contract <- sas_contract(file.path(replay_dir(), "replay.sashiny.yml"))
  started <- as.POSIXct("2015-07-30 12:00:00", tz = "UTC")
  result <- sas_engine_result(contract, "warning",
    log = "WARNING: x\n", macros = list(CASE = "1"), sas_version = "9.04.01M0P061913",
    engine = "batch", run_id = "r1", started_at = started, ended_at = "2015-07-30T12:00:05Z"
  )
  expect_s3_class(result, "sashiny_result")
  meta <- result$metadata
  expect_identical(result$run_id, "r1")
  expect_identical(meta$status, "warning")
  expect_identical(meta$started_at, "2015-07-30T12:00:00Z")
  expect_identical(meta$ended_at, "2015-07-30T12:00:05Z")
  expect_identical(meta$contract_sha256, .sashiny_contract_sha256(contract))
  expect_identical(meta$program_sha256, .sashiny_program_sha256(contract))
  expect_identical(meta$engine_version, as.character(utils::packageVersion("SAShiny")))
  expect_identical(meta$collect_errors, list())
  expect_error(sas_engine_result(contract, "ok"), class = "sashiny_error_engine")
  expect_error(sas_engine_result(list(), "success"), class = "sashiny_error_engine")
})

test_that("sas_record() writes a recording that the replay engine replays", {
  skip_without_replay_fixtures()
  dir <- copy_replay_contract()
  contract <- sas_contract(file.path(dir, "replay.sashiny.yml"))
  live <- sas_run(contract, test_batch_engine(), list(case = 4))
  recordings <- tempfile("recs")
  path <- sas_record(recordings, contract, live)
  # The section 8.3 key is unchanged: the same contract bytes and macros give
  # the file name the shared fixture uses for case 4.
  fixture <- jsonlite::fromJSON(file.path(replay_dir(), "cases.json"), simplifyVector = FALSE)
  expect_true(file.exists(path))
  key <- .sashiny_recording_key(contract, list(CASE = "4"))
  expect_identical(basename(path), paste0(key, ".json"))
  expect_true(file.exists(file.path(replay_dir(), "recordings", basename(path))))
  rec <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  expect_identical(rec$sashiny_recording, 1L)
  expect_identical(rec$sas_version, "9.04.01M0P061913")
  expect_identical(rec$program_sha256, .sashiny_program_sha256(contract))
  expect_match(rec$recorded_at, "^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\dZ$")
  replayed <- outside_tests(sas_run(contract, sas_replay(recordings), list(case = 4)))
  expect_identical(replayed$metadata$recording, "replayed")
  expect_identical(replayed$log, live$log)
  expect_identical(replayed$outputs, live$outputs)
  expect_identical(
    replayed$metadata$notice,
    paste0("Replayed from 9.04.01M0P061913, recorded ", rec$recorded_at, ".")
  )
  expect_length(fixture$cases, 10L)
})

test_that("sas_record() writes empty macros and outputs as JSON objects", {
  contract <- sas_contract(system.file("examples", "minimal", "minimal.sashiny.yml",
    package = "SAShiny"
  ))
  contract$data$inputs <- NULL
  result <- sas_engine_result(contract, "success", sas_version = "9.04.01M0P061913")
  path <- sas_record(tempfile("recs"), contract, result)
  text <- paste(readLines(path, encoding = "UTF-8"), collapse = "\n")
  expect_match(text, '"macros": \\{\\}')
  expect_match(text, '"outputs": \\{\\}')
})

test_that("sas_record() refuses results that did not come from a live run", {
  skip_without_replay_fixtures()
  dir <- copy_replay_contract()
  contract <- sas_contract(file.path(dir, "replay.sashiny.yml"))
  recs <- tempfile("recs")
  ok <- sas_engine_result(contract, "success", macros = list(CASE = "1"),
    sas_version = "9.04.01M0P061913"
  )
  no_version <- sas_engine_result(contract, "success", macros = list(CASE = "1"))
  expect_error(sas_record(recs, contract, no_version), "no SAS version")
  replayed <- sas_run(contract, sas_replay(file.path(replay_dir(), "recordings")), list(case = 1))
  expect_identical(replayed$metadata$recording, "replayed")
  expect_error(sas_record(recs, contract, replayed), "itself a replay")
  hit <- ok
  hit$metadata$cache_hit <- TRUE
  expect_error(sas_record(recs, contract, hit), "cache hit")
  other <- ok
  other$metadata$contract_sha256 <- strrep("0", 64)
  expect_error(sas_record(recs, contract, other), "different contract")
  cat("/* changed */\n", file = file.path(dir, "replay.sas"), append = TRUE)
  expect_error(sas_record(recs, contract, ok), "different version of the program",
    class = "sashiny_error_engine"
  )
  expect_false(dir.exists(recs))
})

test_that("register, record and replay work with the installed example only", {
  # Runs everywhere, including R CMD check, where the replay fixtures are absent.
  dir <- tempfile("minimal")
  dir.create(dir)
  example <- system.file("examples", "minimal", package = "SAShiny")
  file.copy(file.path(example, c("minimal.sashiny.yml", "minimal.sas")), dir)
  contract <- sas_contract(file.path(dir, "minimal.sashiny.yml"))
  outside_tests(expect_error(sas_run(contract, test_batch_engine()), "sas_register_engine"))
  on.exit(sas_unregister_engine("test_batch_engine"), add = TRUE)
  sas_register_engine("test_batch_engine", license_ack = TRUE, description = "test stand-in")
  live <- outside_tests(sas_run(contract, test_batch_engine(), list(n_rows = 3)))
  expect_identical(live$metadata$macros, list(N_ROWS = "3"))
  recordings <- tempfile("recs")
  sas_record(recordings, contract, live)
  replayed <- outside_tests(sas_run(contract, sas_replay(recordings), list(n_rows = 3)))
  expect_identical(replayed$metadata$recording, "replayed")
  expect_identical(replayed$outputs, live$outputs)
  expect_match(replayed$metadata$notice, "^Replayed from 9.04.01M0P061913, recorded ")
  missing <- outside_tests(sas_run(contract, sas_replay(recordings), list(n_rows = 4)))
  expect_identical(missing$metadata$recording, "missing")
  cat("/* changed */\n", file = file.path(dir, "minimal.sas"), append = TRUE)
  refused <- sas_run(contract, sas_replay(recordings), list(n_rows = 3))
  expect_identical(refused$metadata$recording, "refused")
})
