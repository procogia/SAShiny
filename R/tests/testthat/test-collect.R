# Result collection helpers against the shared fixtures (spec section 8).

collect_fixture <- function(name) {
  jsonlite::fromJSON(file.path(.sashiny_fixtures(), "collect", name), simplifyVector = FALSE)
}

test_that("log scoping matches the shared fixtures", {
  for (case in collect_fixture("log_scope.json")$cases) {
    expect_identical(.sashiny_scope_log(case$log, case$scope), case$expected, label = case$name)
  }
})

test_that("plot extraction matches the shared fixtures", {
  fixture <- collect_fixture("plots.json")
  for (case in fixture$cases) {
    if (!is.null(case$expected_error)) {
      expect_error(.sashiny_extract_plots(fixture$html, case$select), "graph", label = case$name)
    } else {
      expect_identical(.sashiny_extract_plots(fixture$html, case$select), case$expected,
        label = case$name
      )
    }
  }
})

test_that("the recording key matches the shared fixture", {
  case <- collect_fixture("recording_key.json")
  macros <- stats::setNames(
    lapply(case$macros, function(m) m[[2]]),
    vapply(case$macros, function(m) m[[1]], character(1))
  )
  uploads <- stats::setNames(
    vapply(case$uploads, function(u) u[[2]], character(1)),
    vapply(case$uploads, function(u) u[[1]], character(1))
  )
  text <- .sashiny_recording_key_text(case$contract_sha256, macros, uploads)
  expect_identical(text, case$key_text)
  expect_identical(.sashiny_recording_key_hash(case$contract_sha256, macros, uploads), case$key)
})

test_that("split_log handles every line break", {
  expect_identical(.sashiny_split_log("a\r\nb\rc\nd  \n"), c("a", "b", "c", "d"))
  expect_identical(.sashiny_split_log(""), character(0))
})

test_that("SAS collection code is generated as specified", {
  code <- .sashiny_table_meta_code("WORK", "STATS")
  expect_match(code, 'where libname = "WORK" and memname = "STATS"', fixed = TRUE)
  expect_true(endsWith(code, "quit;\n"))
  fmt <- .sashiny_formatted_table_code("WORK", "STATS", c("a", "b"), 5)
  expect_match(fmt, "set WORK.STATS(obs=5 keep=a b);", fixed = TRUE)
  expect_match(fmt, "_sx_c2 = strip(vvalue(b));", fixed = TRUE)
  expect_match(fmt, "length _sx_c1-_sx_c2 $512;", fixed = TRUE)
  ch <- .sashiny_choices_code(list(dataset = "sashelp.cars", value_column = "make"))
  expect_match(ch, "select distinct make\n", fixed = TRUE)
  expect_match(ch, "outobs=1000", fixed = TRUE)
  lab <- .sashiny_choices_code(list(
    dataset = "sashelp.cars", value_column = "make", label_column = "lbl", max_choices = 5L
  ))
  expect_match(lab, "select distinct make, lbl\n", fixed = TRUE)
})

test_that("build_table produces raw and formatted values", {
  meta <- list(
    list(name = "x", type = "numeric", label = "X", format = ""),
    list(name = "s", type = "character", label = NULL, format = NA)
  )
  raw <- .sashiny_build_table(meta, list(list(1, "a  "), list(NA, NULL)),
    total_rows = 3L, max_rows = 2L, formatted = FALSE
  )
  expect_identical(raw$rows, list(list(1, "a"), list(NULL, NULL)))
  expect_true(raw$truncated)
  expect_identical(raw$columns[[2]], list(name = "s", type = "character", label = "", format = ""))
  fmt <- .sashiny_build_table(meta, list(list(" 1 ", NULL)),
    total_rows = NULL, max_rows = 2L, formatted = TRUE
  )
  expect_identical(fmt$rows, list(list("1", "")))
  expect_false(fmt$truncated)
})

test_that("build_table preserves Unicode whitespace (parity with Python)", {
  meta <- list(list(name = "s", type = "character", label = "", format = ""))
  raw <- .sashiny_build_table(
    meta, list(list("abc\u00a0"), list("abc\u2003"), list("abc ")),
    total_rows = 3L, max_rows = 10L, formatted = FALSE
  )
  expect_identical(raw$rows, list(list("abc\u00a0"), list("abc\u2003"), list("abc")))
  fmt <- .sashiny_build_table(
    meta, list(list("abc\u00a0"), list("abc ")),
    total_rows = 2L, max_rows = 10L, formatted = TRUE
  )
  expect_identical(fmt$rows, list(list("abc\u00a0"), list("abc")))
})

test_that("select_columns matches case-insensitively in contract order", {
  meta <- list(list(name = "A"), list(name = "b"))
  expect_identical(.sashiny_select_columns(meta, NULL), meta)
  expect_identical(.sashiny_select_columns(meta, list("B", "a")), meta[c(2, 1)])
  expect_error(.sashiny_select_columns(meta, "zz"), "not found")
})

test_that("join_remote follows the directory's separator", {
  expect_identical(.sashiny_join_remote("/sas/work/", "a.rtf"), "/sas/work/a.rtf")
  expect_identical(.sashiny_join_remote("C:\\SAS\\Work", "a.rtf"), "C:\\SAS\\Work\\a.rtf")
})

fake_table <- function() {
  .sashiny_build_table(
    list(
      list(name = "id", type = "numeric", label = "Subject", format = ""),
      list(name = "txt", type = "character", label = "", format = "")
    ),
    list(list(1, "a,\"b\""), list(NULL, "c")),
    total_rows = 2L, max_rows = 10L, formatted = FALSE
  )
}

test_that("csv downloads quote fields and leave missing values empty", {
  expect_identical(rawToChar(.sashiny_csv_bytes(fake_table())), "id,txt\n1,\"a,\"\"b\"\"\"\n,c\n")
})

test_that("xlsx downloads round-trip", {
  skip_if_not_installed("openxlsx")
  path <- tempfile(fileext = ".xlsx")
  writeBin(.sashiny_xlsx_bytes(fake_table(), "STATS"), path)
  expect_identical(openxlsx::getSheetNames(path), "STATS")
  df <- openxlsx::read.xlsx(path, sheet = "STATS")
  expect_identical(names(df), c("id", "txt"))
  expect_identical(df$txt, c("a,\"b\"", "c"))
})

test_that("xpt downloads choose version 5 or 8", {
  skip_if_not_installed("haven")
  short <- .sashiny_xpt_bytes(fake_table(), "STATS")
  expect_true(startsWith(rawToChar(short[1:80]), "HEADER RECORD*******LIBRARY HEADER RECORD"))
  long <- .sashiny_xpt_bytes(fake_table(), "A_VERY_LONG_NAME")
  expect_true(grepl("LIBV8", rawToChar(long[1:80])))
})

test_that("download values are base64 with the right MIME type", {
  value <- .sashiny_download_value("out", "csv", charToRaw("a\n"))
  expect_identical(value, list(filename = "out.csv", mime = "text/csv", data = "YQo="))
})
