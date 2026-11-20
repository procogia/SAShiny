# Data frame accessors (spec section 8.7), checked against the shared fixture.

frames_fixture <- function() {
  jsonlite::fromJSON(file.path(.sashiny_fixtures(), "collect", "frames.json"),
    simplifyVector = FALSE)
}

frames_result <- function(fx = frames_fixture()) {
  structure(list(outputs = fx$result$outputs, log = fx$result$log), class = "sashiny_result")
}

r_type <- function(x) {
  if (is.integer(x)) "integer" else if (is.double(x)) "double" else if (is.character(x)) "character" else class(x)[[1]]
}

expect_frame <- function(df, exp, info) {
  expect_identical(names(df), vapply(exp$columns, function(c) c[[1]], ""), info = info)
  expect_identical(unname(vapply(df, r_type, "")), vapply(exp$columns, function(c) c[[2]], ""),
    info = info)
  expect_identical(nrow(df), length(exp$rows), info = info)
  for (i in seq_along(exp$rows)) {
    for (j in seq_along(exp$columns)) {
      want <- exp$rows[[i]][[j]]
      got <- df[[j]][[i]]
      if (is.null(want)) expect_true(is.na(got), info = paste(info, i, j)) else
        expect_equal(got, want, info = paste(info, i, j), ignore_attr = TRUE)
    }
  }
}

test_that("table accessors match the fixture (spec section 8.7)", {
  fx <- frames_fixture()
  for (id in names(fx$expected$table)) {
    exp <- fx$expected$table[[id]]
    df <- sas_result_table(frames_result(fx), id)
    expect_frame(df, exp, id)
    expect_identical(lapply(df, attr, "label"), exp$labels, info = id)
    expect_identical(lapply(df, attr, "format.sas"), exp$formats, info = id)
    expect_identical(as.numeric(attr(df, "total_rows")), as.numeric(exp$total_rows))
    expect_identical(attr(df, "truncated"), exp$truncated)
  }
})

test_that("the log accessor matches the fixture and the status rules", {
  fx <- frames_fixture()
  df <- sas_result_log(frames_result(fx))
  expect_frame(df, fx$expected$log, "log")
  counts <- .sashiny_classify_log(fx$result$log)
  expect_identical(sum(df$type == "ERROR"), counts[["error"]])
  expect_identical(sum(df$type == "WARNING"), counts[["warning"]])
})

test_that("sas_result_outputs converts tables and logs and keeps the rest", {
  fx <- frames_fixture()
  out <- sas_result_outputs(frames_result(fx))
  exp <- fx$expected$outputs
  for (id in unlist(exp$frames)) expect_s3_class(out[[id]], "data.frame")
  for (id in names(exp$log_frames)) {
    expect_frame(out[[id]], list(columns = fx$expected$log$columns, rows = exp$log_frames[[id]]), id)
  }
  for (id in unlist(exp$unchanged)) expect_identical(out[[id]], fx$result$outputs[[id]])
})

test_that("accessor errors name the output (spec section 8.7)", {
  fx <- frames_fixture()
  for (e in fx$expected$errors) {
    expect_error(sas_result_table(frames_result(fx), e$id), e$message, fixed = TRUE)
  }
})

test_that("tibble output keeps the attributes", {
  skip_if_not_installed("tibble")
  df <- sas_result_table(frames_result(), "stats", tibble = TRUE)
  expect_s3_class(df, "tbl_df")
  expect_identical(attr(df, "total_rows"), 1000L)
  expect_identical(attr(df$mean_msrp, "label"), "Mean MSRP")
})
