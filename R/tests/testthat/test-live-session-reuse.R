# Live session-reuse timing check (#130 J1/J2), mirroring
# Python/tests/live/test_live_session_reuse.py. Skipped unless SASHINY_LIVE=1;
# connection settings as in test-demo-live.R.
#
# Runs examples/general/cars_explorer 10 times on one engine and 10 times on a
# pool of two. For each run it records the wall time and the SAS process id,
# taken from a test-only probe program that puts SXPID=&sysjobid; before the
# unchanged example text. A CSV report goes to tempdir().

# TRUE once the persistent R worker (build prompt 1, spec section 6.5) lands.
reuse_fixed <- FALSE

live_probe_contract <- function() {
  skip_if_no_demo_scenarios()
  example <- file.path(.demo_examples(), "general")
  folder <- tempfile("sashiny-reuse-")
  dir.create(folder)
  program <- readLines(file.path(example, "cars_explorer.sas"), warn = FALSE)
  writeLines(c("%put SXPID=&sysjobid;", program), file.path(folder, "probe.sas"))
  data <- yaml::read_yaml(file.path(example, "cars_explorer.sashiny.yml"))
  data$program <- "probe.sas"
  yaml::write_yaml(data, file.path(folder, "probe.sashiny.yml"))
  sas_contract(file.path(folder, "probe.sashiny.yml"))
}

live_series <- function(engine, contract, n = 10L) {
  rows <- lapply(seq_len(n), function(i) {
    t0 <- Sys.time()
    res <- sas_engine_run(engine, contract, list())
    secs <- as.numeric(difftime(Sys.time(), t0, units = "secs"))
    pid <- regmatches(res$log, regexpr("SXPID=\\S+", res$log))
    expect_true(res$status %in% c("success", "warning"), info = res$metadata$engine_error)
    data.frame(run = i, seconds = secs, sas_pid = if (length(pid)) sub("SXPID=", "", pid) else "")
  })
  do.call(rbind, rows)
}

live_summary <- function(label, df) {
  sprintf(
    "%s: %d distinct SAS process id(s); median %.2f s, p90 %.2f s",
    label, length(unique(df$sas_pid)), stats::median(df$seconds),
    stats::quantile(df$seconds, 0.9, names = FALSE)
  )
}

test_that("one engine reuses its SAS session across runs (spec section 6.5)", {
  skip_unless_live()
  contract <- live_probe_contract()
  engine <- live_connect()
  on.exit(sas_engine_close(engine), add = TRUE)
  single <- live_series(engine, contract)
  pool <- sas_pool(sas_connect_env, max_size = 2L)
  on.exit(sas_engine_close(pool), add = TRUE)
  pooled <- live_series(pool, contract)
  report <- file.path(tempdir(), "session-reuse-r.csv")
  utils::write.csv(rbind(
    cbind(mode = "engine", single), cbind(mode = "pool2", pooled)
  ), report, row.names = FALSE)
  message(live_summary("engine", single), "\n", live_summary("pool(max_size=2)", pooled),
    "\nreport: ", report)
  expect_true(all(nzchar(single$sas_pid)))
  skip_if_not(reuse_fixed, "R sessions are not reused until the persistent worker lands")
  expect_identical(length(unique(single$sas_pid)), 1L)
  expect_lte(length(unique(pooled$sas_pid)), 2L)
})
