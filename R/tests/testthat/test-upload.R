# Dataset upload conversion (spec section 7).

upload_spec <- list(
  type = "dataset", target = "work.adsl",
  columns = list(
    list(name = "usubjid", type = "character"),
    list(name = "age", type = "numeric"),
    list(name = "trtsdt", type = "date")
  )
)

write_csv <- function(lines, name = "adsl.csv") {
  path <- file.path(tempfile("sashiny-up-"), name)
  dir.create(dirname(path))
  writeLines(lines, path)
  .sashiny_upload_file(path, name)
}

test_that("uploads resolve from TRUE, paths, fileInput values and upload files", {
  base <- tempdir()
  expect_null(.sashiny_resolve_upload(NULL, upload_spec, base))
  expect_error(.sashiny_resolve_upload(TRUE, upload_spec, base), "no sample")
  sample <- .sashiny_resolve_upload(TRUE, c(upload_spec, sample = "data/x.csv"), base)
  expect_identical(sample$name, "x.csv")
  expect_identical(sample$path, file.path(base, "data/x.csv"))
  shiny_value <- data.frame(name = "real.csv", datapath = "/tmp/0.csv")
  expect_identical(.sashiny_resolve_upload(shiny_value, upload_spec, base)$name, "real.csv")
  expect_identical(.sashiny_resolve_upload("/tmp/y.CSV", upload_spec, base)$name, "y.CSV")
})

test_that("column names are sanitised like the Python library", {
  expect_identical(
    .sashiny_sanitize_names(c("a b", "1x", "A_B", "\u00e9")),
    c("a_b", "_1x", "A_B_2", "_")
  )
  long <- strrep("x", 40)
  expect_identical(
    .sashiny_sanitize_names(c(long, long)),
    c(strrep("x", 32), paste0(strrep("x", 30), "_2"))
  )
})

test_that("CSV uploads convert declared and inferred columns", {
  upload <- write_csv(c(
    "USUBJID,AGE,TRTSDT,extra num,note,hex",
    "S1,45,2024-01-02,1.5,hi,0x1A",
    "S2,,,2,,1"
  ))
  read <- .sashiny_read_upload(upload, upload_spec)
  df <- read$df
  expect_identical(names(df), c("USUBJID", "AGE", "TRTSDT", "extra_num", "note", "hex"))
  expect_identical(read$datetimes, list(TRTSDT = "date"))
  expect_identical(df$AGE, c(45, NA))
  expect_s3_class(df$TRTSDT, "Date")
  expect_true(is.numeric(df$extra_num))
  expect_identical(df$note, c("hi", ""))
  expect_true(is.character(df$hex))
})

test_that("bad uploads are rejected with V014 messages", {
  expect_error(
    .sashiny_read_upload(write_csv(c("USUBJID,AGE", "S1,40")), upload_spec),
    "no column trtsdt"
  )
  expect_error(
    .sashiny_read_upload(write_csv(c("USUBJID,AGE,TRTSDT", "S1,old,2024-01-01")), upload_spec),
    "not numbers"
  )
  expect_error(
    .sashiny_read_upload(write_csv(c("USUBJID,AGE,TRTSDT", "S1,4,01/02/2024")), upload_spec),
    "YYYY-MM-DD"
  )
  xlsx_only <- upload_spec
  xlsx_only$accept <- list("xlsx")
  expect_error(.sashiny_read_upload(write_csv("a"), xlsx_only), "not accepted")
  expect_error(
    .sashiny_read_upload(.sashiny_upload_file(tempfile(fileext = ".csv")), upload_spec),
    "file not found"
  )
  big <- write_csv(c("a", rep("1", 1000)))
  expect_error(
    .sashiny_read_upload(big, list(type = "dataset", target = "work.a", max_size_mb = 0.0001)),
    "MB"
  )
  err <- tryCatch(.sashiny_read_upload(write_csv("a"), xlsx_only), error = function(e) e)
  expect_s3_class(err, "sashiny_upload_error")
})

test_that("xlsx and xpt uploads are read", {
  skip_if_not_installed("openxlsx")
  skip_if_not_installed("haven")
  dir <- tempfile("sashiny-up-")
  dir.create(dir)
  df <- data.frame(USUBJID = "S1", AGE = 50, TRTSDT = as.Date("2024-03-01"))
  openxlsx::write.xlsx(df, file.path(dir, "adsl.xlsx"))
  read <- .sashiny_read_upload(.sashiny_upload_file(file.path(dir, "adsl.xlsx")), upload_spec)
  expect_identical(read$df$AGE, 50)
  expect_identical(read$df$TRTSDT, as.Date("2024-03-01"))
  haven::write_xpt(df, file.path(dir, "adsl.xpt"))
  read <- .sashiny_read_upload(.sashiny_upload_file(file.path(dir, "adsl.xpt")), upload_spec)
  expect_identical(read$df$USUBJID, "S1")
  bad <- file.path(dir, "bad.xlsx")
  writeLines("not a workbook", bad)
  expect_error(.sashiny_read_upload(.sashiny_upload_file(bad), upload_spec), "could not read")
})
