# Live SAS checks of the demo scenarios, mirroring Python/tests/live.
#
# Skipped unless SASHINY_LIVE=1. Connection settings (credentials always come
# from ~/.authinfo):
#   SASHINY_PROFILE       oda | viya | sas94           (required)
#   SASHINY_ODA_REGION    us1 | us2 | eu1 | ap1 | ap2  (oda; default us1)
#   SASHINY_VIYA_URL, SASHINY_VIYA_CONTEXT             (viya)
#   SASHINY_SAS94_HOST, SASHINY_SAS94_PORT, SASHINY_SAS94_SASPATH (sas94)
#   SASHINY_JAVA          Java executable for IOM      (optional)
#   SASHINY_RECORD_TO     directory for recordings     (default: a temp dir)

skip_unless_live <- function() {
  skip_on_cran()
  if (!identical(Sys.getenv("SASHINY_LIVE"), "1")) skip("live SAS tests need SASHINY_LIVE=1")
  skip_if_no_demo_scenarios()
}

.live_env <- function(name, default = NULL) {
  value <- Sys.getenv(name, unset = "")
  if (nzchar(value)) value else default
}

live_connect <- function(record_to = NULL) {
  profile <- .live_env("SASHINY_PROFILE", "")
  java <- .live_env("SASHINY_JAVA")
  switch(profile,
    oda = sas_connect("oda", region = .live_env("SASHINY_ODA_REGION", "us1"), java = java,
      record_to = record_to
    ),
    viya = sas_connect("viya",
      url = .live_env("SASHINY_VIYA_URL"), context = .live_env("SASHINY_VIYA_CONTEXT"),
      record_to = record_to
    ),
    sas94 = sas_connect("sas94",
      host = .live_env("SASHINY_SAS94_HOST"),
      port = as.integer(.live_env("SASHINY_SAS94_PORT", "8591")),
      saspath = .live_env("SASHINY_SAS94_SASPATH"), java = java, record_to = record_to
    ),
    stop("set SASHINY_PROFILE to oda, viya or sas94", call. = FALSE)
  )
}

# One recorded session and its runs, shared by the tests in this file.
.live <- new.env(parent = emptyenv())

live_runs <- function() {
  if (is.null(.live$runs)) {
    .live$record_dir <- .live_env("SASHINY_RECORD_TO", tempfile("sashiny-recordings-"))
    dir.create(.live$record_dir, showWarnings = FALSE, recursive = TRUE)
    .live$engine <- live_connect(record_to = .live$record_dir)
    scenarios <- demo_scenarios()
    .live$runs <- stats::setNames(lapply(scenarios, function(s) {
      sas_engine_run(.live$engine, sas_contract(s$contract_path), s$values, .demo_today,
        uploads = s$uploads
      )
    }), vapply(scenarios, function(s) s$id, ""))
  }
  .live$runs
}

test_that("every scenario is demo-ready on live SAS", {
  skip_unless_live()
  runs <- live_runs()
  expect_true(nzchar(.sashiny_saspy_version(.live$engine)), "no SAS version reported")
  for (s in demo_scenarios()) {
    problems <- demo_check_result(runs[[s$id]], sas_contract(s$contract_path), s)
    expect_identical(problems, character(0), info = s$title)
  }
})

test_that("the SAS program ran unchanged", {
  skip_unless_live()
  runs <- live_runs()
  for (s in demo_scenarios()) {
    contract <- sas_contract(s$contract_path)
    on_disk <- as.character(openssl::sha256(file(file.path(contract$base_dir, contract$data$program))))
    expect_identical(runs[[s$id]]$metadata$program_sha256, on_disk, info = s$id)
  }
})

test_that("each run's recording replays offline with identical outputs", {
  skip_unless_live()
  runs <- live_runs()
  replay <- sas_engine_mock(.live$record_dir)
  for (s in demo_scenarios()) {
    again <- sas_engine_run(replay, sas_contract(s$contract_path), s$values, .demo_today,
      uploads = s$uploads
    )
    expect_identical(again$metadata$recording, "replayed", info = s$id)
    expect_identical(again$status, runs[[s$id]]$status, info = s$id)
    expect_identical(again$outputs, runs[[s$id]]$outputs, info = s$id)
  }
})

test_that("WORK is reset between runs", {
  skip_unless_live()
  runs <- live_runs()
  s <- demo_scenario("general")
  again <- sas_engine_run(.live$engine, sas_contract(s$contract_path), s$values, .demo_today)
  expect_identical(demo_tables(again), demo_tables(runs$general))
  expect_false(identical(demo_tables(again), demo_tables(runs[["general-msrp-40000"]])))
})

test_that("invalid input is rejected before SAS and the session stays usable", {
  skip_unless_live()
  live_runs()
  s <- demo_scenario("general")
  contract <- sas_contract(s$contract_path)
  bad <- sas_engine_run(.live$engine, contract, utils::modifyList(s$values, list(min_msrp = -5)),
    .demo_today
  )
  expect_identical(bad$status, "error")
  expect_true(length(bad$metadata$issues) > 0)
  expect_null(bad$metadata$syscc)
  good <- sas_engine_run(.live$engine, contract, s$values, .demo_today)
  expect_identical(good$status, "success")
})

test_that("a user-uploaded xlsx gives the same AML results as the sample", {
  skip_unless_live()
  skip_if_not_installed("openxlsx")
  runs <- live_runs()
  s <- demo_scenario("aml")
  contract <- sas_contract(s$contract_path)
  sample <- file.path(contract$base_dir, contract$data$inputs$transactions$sample)
  xlsx <- tempfile(fileext = ".xlsx")
  openxlsx::write.xlsx(utils::read.csv(sample, colClasses = "character"), xlsx)
  fresh <- live_connect()
  on.exit(sas_engine_close(fresh), add = TRUE)
  result <- sas_engine_run(fresh, contract, s$values, .demo_today,
    uploads = list(transactions = xlsx)
  )
  expect_identical(demo_check_result(result, contract, s), character(0))
  expect_identical(demo_tables(result), demo_tables(runs$aml))
})

test_that("a fresh session gives the same results", {
  skip_unless_live()
  runs <- live_runs()
  fresh <- live_connect()
  on.exit(sas_engine_close(fresh), add = TRUE)
  for (s in Filter(function(s) s$primary, demo_scenarios())) {
    result <- sas_engine_run(fresh, sas_contract(s$contract_path), s$values, .demo_today,
      uploads = s$uploads
    )
    expect_identical(demo_tables(result), demo_tables(runs[[s$id]]), info = s$id)
  }
})
