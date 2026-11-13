# End-to-end tests of the saspy engine against a fake session (spec 6-8).

fake_engine <- function(fake = fake_session(), ...) {
  sas_engine_saspy(list(java = "java"), session_factory = function() fake, ...)
}

test_that("a new session turns notes on first (ODA starts with NONOTES)", {
  fake <- fake_session()
  sas_engine_run(fake_engine(fake), fake_contract(), list(min_age = 30, make = "BMW"),
    today = .sashiny_today
  )
  expect_identical(fake$submitted[[1]], .sashiny_session_setup_code)
  expect_identical(sum(fake$submitted == .sashiny_session_setup_code), 1L)
})

test_that("a full run collects every output type", {
  fake <- fake_session()
  contract <- fake_contract()
  result <- sas_engine_run(fake_engine(fake), contract,
    list(min_age = 30, make = "BMW"),
    today = .sashiny_today, uploads = list(adsl = TRUE), run_id = "r1"
  )
  expect_identical(result$status, "success")
  out <- result$outputs

  expect_identical(out$stats$columns[[1]], list(
    name = "age", type = "numeric", label = "Age (y)", format = "BEST12."
  ))
  expect_identical(vapply(out$stats$columns, function(c) c$name, ""), c("age", "name"))
  expect_identical(out$stats$rows, list(list(40, "Ann"), list(NULL, "Bo")))
  expect_identical(out$stats$total_rows, 3L)
  expect_true(out$stats$truncated)

  expect_true(out$stats_fmt$formatted)
  expect_identical(out$stats_fmt$rows[[1]][[1]], "fmt:Ann")

  expect_identical(out$missing, list(error = "dataset WORK.NOPE not found"))
  expect_identical(result$metadata$collect_errors, list("missing: dataset WORK.NOPE not found"))

  expect_identical(vapply(out$graphs, function(p) p$mime, ""), c("image/png", "image/svg+xml"))
  expect_identical(out$second, out$graphs[2])
  expect_true(startsWith(out$report, "<html>"))
  expect_identical(out$log, list(list(
    level = "note", text = "NOTE: The data set WORK.OUT has 2 observations."
  )))

  csv <- strsplit(rawToChar(openssl::base64_decode(out$csv$data)), "\n")[[1]]
  expect_identical(out$csv$filename, "stats.csv")
  expect_identical(csv[1:2], c("name,age,trtsdt", "Ann,40,23377"))
  expect_identical(rawToChar(openssl::base64_decode(out$data$data)), "SAS7BDAT")
  expect_identical(out$data$filename, "data.sas7bdat")
  expect_identical(rawToChar(openssl::base64_decode(out$rtf$data)), "{\\rtf1}")

  meta <- result$metadata
  expect_identical(meta$sas_version, "9.04.01M8P011923")
  expect_identical(meta$macros$MIN_AGE, "30")
  expect_identical(meta$macros$MAKE, "BMW")
  expect_identical(nchar(meta$contract_sha256), 64L)
  expect_identical(nchar(meta$program_sha256), 64L)
  expect_identical(meta$syscc, 0L)

  expect_identical(fake$uploaded$WORK.ADSL$df$age, c(40, 50))
  expect_false(any(startsWith(names(fake$datasets), "WORK._SX_")))
})

test_that("choices_from validation uses the choices read from SAS", {
  engine <- fake_engine()
  contract <- fake_contract()
  expect_identical(sas_engine_choices(engine, contract), list(make = list(
    list(value = "Audi", label = "Audi"),
    list(value = "BMW", label = "BMW"),
    list(value = "Saab", label = "Saab")
  )))
  bad <- sas_engine_run(engine, contract, list(min_age = 30, make = "Fiat"), today = .sashiny_today)
  expect_identical(bad$status, "error")
  expect_match(bad$metadata$issues[[1]]$code, "^V")
})

test_that("user files are uploaded and bad files are reported as V014", {
  fake <- fake_session()
  engine <- fake_engine(fake)
  contract <- fake_contract()
  own <- tempfile(fileext = ".csv")
  writeLines(c("age", "33"), own)
  ok <- sas_engine_run(engine, contract, list(min_age = 1),
    today = .sashiny_today, uploads = list(adsl = own)
  )
  expect_identical(ok$status, "success")
  expect_identical(fake$uploaded$WORK.ADSL$df$age, 33)
  bad <- tempfile(fileext = ".csv")
  writeLines(c("age", "old"), bad)
  failed <- sas_engine_run(engine, contract, list(min_age = 1),
    today = .sashiny_today, uploads = list(adsl = bad)
  )
  expect_identical(failed$status, "error")
  expect_identical(failed$metadata$issues[[1]]$code, "V014")
})

test_that("run status follows syscc and the log", {
  fake <- fake_session()
  fake$syscc <- 4L
  fake$program_log <- "WARNING: Something."
  result <- sas_engine_run(fake_engine(fake), fake_contract(), list(min_age = 1),
    today = .sashiny_today
  )
  expect_identical(result$status, "warning")
})

test_that("a broken session is reported and replaced on the next run", {
  starts <- 0L
  factory <- function() {
    starts <<- starts + 1L
    fake <- fake_session()
    submit <- fake$submit
    fake$submit <- function(code, results = "HTML") {
      if (grepl("SASHINY-BEGIN", code, fixed = TRUE)) stop("lost connection")
      submit(code, results)
    }
    fake
  }
  engine <- sas_engine_saspy(list(), session_factory = factory)
  contract <- fake_contract()
  result <- sas_engine_run(engine, contract, list(min_age = 1), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "lost connection")
  sas_engine_run(engine, contract, list(min_age = 1), today = .sashiny_today)
  expect_identical(starts, 2L)
})

test_that("a failed session is ended before it is replaced", {
  ended <- 0L
  fake <- fake_session()
  submit <- fake$submit
  fake$submit <- function(code, results = "HTML") {
    if (grepl("SASHINY-BEGIN", code, fixed = TRUE)) stop("lost connection")
    submit(code, results)
  }
  endsas <- fake$endsas
  fake$endsas <- function() {
    ended <<- ended + 1L
    endsas()
  }
  engine <- sas_engine_saspy(list(), session_factory = function() fake)
  result <- sas_engine_run(engine, fake_contract(), list(min_age = 1), today = .sashiny_today)
  expect_identical(result$status, "error")
  expect_identical(ended, 1L)
})

test_that("live runs are recorded and replayed by the mock engine", {
  rec <- tempfile("sashiny-rec-")
  contract <- fake_contract()
  live <- sas_engine_run(fake_engine(record_to = rec), contract,
    list(min_age = 30, make = "BMW"),
    today = .sashiny_today, uploads = list(adsl = TRUE)
  )
  files <- list.files(rec, pattern = "[.]json$", full.names = TRUE)
  expect_length(files, 1L)
  key <- .sashiny_recording_key(contract, live$metadata$macros,
    list(adsl = file.path(contract$base_dir, "adsl.csv"))
  )
  expect_identical(basename(files), paste0(key, ".json"))
  payload <- jsonlite::fromJSON(files, simplifyVector = FALSE)
  expect_identical(payload$sashiny_recording, 1L)

  mock <- sas_engine_mock(rec, choices = list(make = c("BMW", "Audi")))
  replay <- sas_engine_run(mock, contract, list(min_age = 30, make = "BMW"),
    today = .sashiny_today, uploads = list(adsl = TRUE)
  )
  expect_identical(replay$metadata$recording, "replayed")
  expect_identical(replay$status, live$status)
  expect_equal(replay$outputs$stats$rows, live$outputs$stats$rows)
  expect_identical(replay$outputs$csv, live$outputs$csv)
  expect_identical(replay$outputs$log, live$outputs$log)
  expect_identical(replay$outputs$missing, live$outputs$missing)

  other <- sas_engine_run(mock, contract, list(min_age = 31, make = "BMW"),
    today = .sashiny_today, uploads = list(adsl = TRUE)
  )
  expect_identical(other$metadata$recording, "missing")
  expect_length(other$outputs, 0L)
})

test_that("closing the engine ends the session", {
  fake <- fake_session()
  engine <- fake_engine(fake)
  sas_engine_run(engine, fake_contract(), list(min_age = 1), today = .sashiny_today)
  sas_engine_close(engine)
  expect_true(fake$ended)
  expect_null(engine$sas)
})

test_that("the saspy configuration file is valid Python", {
  dir <- tempfile("sashiny-cfg-")
  dir.create(dir)
  cfg <- list(java = "/usr/bin/java", iomport = 8591L, iomhost = c("a", "b"))
  path <- .sashiny_write_cfgfile(cfg, "oda", dir)
  text <- readLines(path)
  expect_identical(text[[3]], "SAS_config_names = ['oda']")
  expect_match(text[[4]], "oda = json.loads(r'''{\"java\":\"/usr/bin/java\"", fixed = TRUE)
  expect_error(.sashiny_write_cfgfile(list(), "not valid", dir), "identifier")
  skip_on_cran()
  skip_on_os("windows")
  python <- Sys.which("python3")
  skip_if(!nzchar(python), "python3 not available")
  out <- system2(python, c("-c", shQuote(sprintf(
    paste(
      "import runpy; ns = runpy.run_path(%s);",
      "print(ns['oda']['iomhost'][1], ns['SAS_config_names'][0])"
    ),
    shQuote(path, type = "sh")
  ))), stdout = TRUE)
  expect_identical(out, "b oda")
})

test_that("dates and times convert back to SAS numbers", {
  expect_identical(.sashiny_sas_number(as.POSIXct("1960-01-02", tz = "UTC"), "DATE9."), 1)
  utc <- function(x) as.POSIXct(x, tz = "UTC")
  expect_identical(.sashiny_sas_number(utc("1960-01-01 00:01:00"), "DATETIME20."), 60)
  expect_identical(.sashiny_sas_number(utc("2000-01-01 01:00:00"), "TIME8."), 3600)
  expect_identical(.sashiny_sas_number(as.Date("1960-01-11"), ""), 10)
  expect_identical(.sashiny_sas_number(as.difftime(90, units = "secs"), "TIME8."), 90)
  expect_identical(.sashiny_sas_number(5, ""), 5)
  expect_null(.sashiny_sas_number(NULL, ""))
})

test_that("the pre-flight check requires Java for IOM connections", {
  expect_error(.sashiny_preflight(list(iomhost = "h", java = "")), "Java was not found")
  expect_error(.sashiny_preflight(list(iomhost = "h")), "Java was not found")
  expect_true(.sashiny_preflight(list(url = "https://viya")))
})

test_that("the pre-flight check requires an authinfo entry", {
  authinfo <- tempfile()
  cfg <- list(iomhost = "h", java = "java", authkey = "oda")
  expect_error(.sashiny_preflight(cfg, authinfo), "no credentials for 'oda'")
  writeLines(c("viya user a password b", "oda user me password pw"), authinfo)
  expect_true(.sashiny_preflight(cfg, authinfo))
  unlink(authinfo)
})

test_that("a missing Java is reported on the result, before saspy is imported", {
  engine <- sas_engine_saspy(list(iomhost = "h", java = "", authkey = "oda"))
  result <- sas_engine_run(engine, fake_contract(), list(min_age = 30, make = "BMW"),
    today = .sashiny_today, uploads = list(adsl = TRUE)
  )
  expect_identical(result$status, "error")
  expect_match(result$metadata$engine_error, "Java was not found")
})

test_that("empty reticulate-converted tables (nrow is NULL) collect cleanly (issue #17)", {
  fake <- fake_session()
  sd2df <- fake$sd2df
  fake$sd2df <- function(table, libref = "WORK", dsopts = NULL) {
    if (identical(toupper(table), "_SX_COLS") && is.null(fake$datasets[["WORK._SX_COLS"]]) ||
        identical(nrow(fake$datasets[["WORK._SX_COLS"]]), 0L) && identical(toupper(table), "_SX_COLS")) {
      return(list(varnum = list(), name = list(), type = list(), format = list(), label = list()))
    }
    if (identical(toupper(table), "STATS")) {
      return(list(name = list(), age = list(), trtsdt = list()))
    }
    if (identical(toupper(table), "_SX_NOBS")) {
      return(list(nlobs = list(0)))
    }
    sd2df(table, libref, dsopts)
  }
  result <- sas_engine_run(fake_engine(fake), fake_contract(),
    list(min_age = 30, make = "BMW"),
    today = .sashiny_today
  )
  expect_identical(result$outputs$stats$rows, list())
  expect_identical(result$outputs$stats$total_rows, 0L)
  expect_false(result$outputs$stats$truncated)
  expect_identical(result$outputs$missing, list(error = "dataset WORK.NOPE not found"))
})
