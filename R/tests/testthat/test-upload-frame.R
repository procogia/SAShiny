# Data frames as dataset inputs (spec sections 6.10 and 7.1).

frame_cases <- function() {
  path <- file.path(.sashiny_fixtures(), "frames", "cases.json")
  testthat::skip_if_not(file.exists(path), "frame fixtures are only in the source repository")
  jsonlite::fromJSON(path, simplifyVector = FALSE)$cases
}

# A data frame from a case's columns (frames/cases.json).
frame_from_case <- function(columns) {
  cols <- lapply(columns, function(col) {
    v <- col$values
    nul <- vapply(v, is.null, logical(1))
    fill <- function(empty, conv) {
      out <- rep(empty, length(v))
      if (any(!nul)) out[!nul] <- conv(unlist(v[!nul]))
      out
    }
    switch(col$type,
      character = fill(NA_character_, as.character),
      factor = factor(fill(NA_character_, as.character)),
      integer = fill(NA_integer_, as.integer),
      double = fill(NA_real_, as.numeric),
      logical = fill(NA, as.logical),
      date = as.Date(fill(NA_character_, as.character)),
      datetime = {
        s <- fill(NA_character_, as.character)
        whole <- sub("(\\.[0-9]+)?Z$", "", s)
        has_frac <- !is.na(s) & grepl("\\.[0-9]+Z$", s)
        frac <- rep(0, length(s))
        frac[has_frac] <- as.numeric(sub("^.*(\\.[0-9]+)Z$", "0\\1", s[has_frac]))
        as.POSIXct(whole, format = "%Y-%m-%dT%H:%M:%S", tz = "UTC") + frac
      }
    )
  })
  names(cols) <- vapply(columns, `[[`, character(1), "name")
  as.data.frame(cols, check.names = FALSE, stringsAsFactors = FALSE)
}

test_that("every frame case writes the expected CSV bytes", {
  for (case in frame_cases()) {
    frame <- frame_from_case(case$columns)
    got <- .sashiny_frame_csv(frame)
    want <- charToRaw(enc2utf8(case$csv))
    expect_identical(got, want, label = case$name)
  }
})

test_that("every frame case reads back with one row per value", {
  # A one-column frame's missing rows are empty lines and must stay rows (spec section 7, #164).
  for (case in frame_cases()) {
    path <- tempfile(fileext = ".csv")
    writeBin(charToRaw(enc2utf8(case$csv)), path)
    df <- .sashiny_read_upload(.sashiny_upload_file(path, "x.csv"),
                               list(type = "dataset", target = "work.x"))$df
    expect_identical(dim(df), c(length(case$columns[[1]]$values), length(case$columns)),
                     label = case$name)
  }
})

test_that("a one-column data frame keeps its missing rows", {
  spec <- list(type = "dataset", target = "work.adsl",
               columns = list(list(name = "age", type = "numeric")))
  upload <- .sashiny_resolve_upload(data.frame(AGE = c(30, NA, 41)), spec, tempfile(), "adsl")
  expect_identical(.sashiny_read_upload(upload, spec)$df$AGE, c(30, NA, 41))
})

test_that("a tibble writes the same bytes as a data frame", {
  skip_if_not_installed("tibble")
  frame <- frame_from_case(frame_cases()[[1]]$columns)
  expect_identical(.sashiny_frame_csv(tibble::as_tibble(frame)), .sashiny_frame_csv(frame))
})

test_that("data frames that cannot be written are upload errors (V014)", {
  expect_error(.sashiny_frame_csv(data.frame(x = c(1, Inf))), "infinite", class = "sashiny_upload_error")
  lst <- data.frame(id = 1:2)
  lst$items <- list(1, 2)
  expect_error(.sashiny_frame_csv(lst), "column 'items' has a type", class = "sashiny_upload_error")
  expect_error(.sashiny_frame_csv(data.frame(z = complex(real = 1, imaginary = 1))),
               "column 'z'", class = "sashiny_upload_error")
  expect_error(.sashiny_frame_csv(data.frame()), "no columns", class = "sashiny_upload_error")
  expect_error(.sashiny_frame_csv("adsl.csv"), "must be a data frame", class = "sashiny_upload_error")
})

dataset_contract <- function() {
  sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "dataset", "contract.sashiny.yml"))
}

test_that("sas_run() accepts a data frame for a dataset input", {
  adsl <- data.frame(USUBJID = c("S-001", "S-002"), AGE = c(54, 61),
                     TRTSDT = as.Date(c("2026-01-15", "2026-02-01")))
  result <- sas_run(dataset_contract(), .sashiny_engine_mock(), uploads = list(adsl = adsl))
  expect_identical(result$status, "success")
  expect_length(result$metadata$issues %||% list(), 0)
})

test_that("a data frame missing a declared column is V014", {
  result <- sas_run(dataset_contract(), .sashiny_engine_mock(),
                    uploads = list(adsl = data.frame(USUBJID = "S-001")))
  expect_identical(result$status, "error")
  codes <- vapply(result$metadata$issues, `[[`, character(1), "code")
  expect_true("V014" %in% codes)
})

test_that("the same frame gives the same recording key as the same CSV file", {
  # The upload's SHA-256 is part of the key (spec 8.3): a frame and a file with
  # its canonical bytes must agree, so R and Python share recordings.
  adsl <- data.frame(USUBJID = "S-001", AGE = 54, TRTSDT = as.Date("2026-01-15"))
  path <- file.path(withr::local_tempdir(), "adsl.csv")
  writeBin(.sashiny_frame_csv(adsl), path)
  files_frame <- .sashiny_resolve_files(dataset_contract(), list(adsl = adsl))
  files_path <- .sashiny_resolve_files(dataset_contract(), list(adsl = path))
  expect_identical(
    unname(tools::md5sum(files_frame$adsl$path)),
    unname(tools::md5sum(files_path$adsl$path))
  )
  expect_identical(files_frame$adsl$name, "adsl.csv")
})

test_that("values() can supply a data frame for a dataset input", {
  skip_if_not_installed("shiny")
  adsl <- data.frame(USUBJID = c("S-001", "S-002"), AGE = c(54, 61),
                     TRTSDT = as.Date(c("2026-01-15", "2026-02-01")))
  ext <- shiny::reactiveVal(list(adsl = adsl))
  shiny::testServer(sas_program_server,
    args = list(contract = dataset_contract(), engine = .sashiny_engine_mock(),
                values = ext, hide_inputs = TRUE), {
      session$setInputs(run = 1)
      expect_identical(session$returned$status(), "success")
      # The upload control of the supplied dataset is hidden.
      expect_match(as.character(output$hide__inputs$html), "#proxy1-in__adsl", fixed = TRUE)

      # NULL removes it: the required dataset is then missing (V001).
      ext(list(adsl = NULL))
      session$setInputs(run = 2)
      expect_identical(session$returned$status(), "error")
      codes <- vapply(session$returned$result()$metadata$issues, `[[`, character(1), "code")
      expect_true("V001" %in% codes)

      # Anything else for a dataset id is V014.
      ext(list(adsl = "adsl.csv"))
      session$setInputs(run = 3)
      codes <- vapply(session$returned$result()$metadata$issues, `[[`, character(1), "code")
      expect_true("V014" %in% codes)
    }
  )
})
