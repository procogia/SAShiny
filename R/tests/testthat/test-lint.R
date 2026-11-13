# Advisory lint (spec section 10).

lint_codes <- function(issues) {
  vapply(issues, function(i) i$code, character(1))
}

lint_data <- function(...) {
  base <- list(
    sashiny = 1,
    program = "x.sas",
    title = "t",
    inputs = list(min_msrp = list(type = "numeric", label = "Min MSRP")),
    outputs = list(log = list(type = "log"))
  )
  utils::modifyList(base, list(...))
}

test_that("a clean program returns no findings", {
  data <- lint_data()
  program <- "proc print data=sashelp.class; where msrp > &MIN_MSRP; run;"
  expect_identical(sashiny_lint(data, program), list())
})

test_that("L001 flags an assignment outside a %symexist guard", {
  data <- lint_data()
  program <- "%let MIN_MSRP = 5;\nproc print data=sashelp.class; run;"
  expect_true("L001" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L001 ignores a %symexist guard", {
  data <- lint_data()
  program <- paste(
    "%if not %symexist(MIN_MSRP) %then %do;",
    "  %let MIN_MSRP = 5;",
    "%end;",
    "proc print data=sashelp.class; run;",
    sep = "\n"
  )
  expect_false("L001" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L001 flags a call symputx assignment", {
  data <- lint_data()
  program <- "data _null_; call symputx('MIN_MSRP', '5'); run;"
  expect_true("L001" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L002 flags an unreferenced macro", {
  data <- lint_data()
  program <- "proc print data=sashelp.class; run;"
  expect_true("L002" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L002 ignores a referenced macro", {
  data <- lint_data()
  program <- "proc print data=sashelp.class; where msrp > &MIN_MSRP; run;"
  expect_false("L002" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L003 flags an uncreated WORK dataset", {
  data <- lint_data(outputs = list(
    log = list(type = "log"),
    tbl = list(type = "table", from = "work.summary")
  ))
  program <- "proc print data=sashelp.class; run;"
  expect_true("L003" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L003 ignores a created dataset", {
  data <- lint_data(outputs = list(
    log = list(type = "log"),
    tbl = list(type = "table", from = "work.summary")
  ))
  program <- "data summary; set sashelp.class; run;"
  expect_false("L003" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L003 ignores a dataset input target", {
  data <- lint_data(
    inputs = list(
      min_msrp = list(type = "numeric", label = "Min MSRP"),
      ds = list(type = "dataset", label = "Data", target = "summary")
    ),
    outputs = list(
      log = list(type = "log"),
      tbl = list(type = "table", from = "work.summary")
    )
  )
  program <- "proc print data=sashelp.class; run;"
  expect_false("L003" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L003 ignores a permanent library", {
  data <- lint_data(outputs = list(
    log = list(type = "log"),
    tbl = list(type = "table", from = "mylib.summary")
  ))
  program <- "proc print data=sashelp.class; run;"
  expect_false("L003" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L004 flags multiple rtf/pdf downloads", {
  data <- lint_data(outputs = list(
    log = list(type = "log"),
    a = list(type = "download", format = "rtf"),
    b = list(type = "download", format = "pdf")
  ))
  program <- "proc print data=sashelp.class; run;"
  expect_true("L004" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L004 ignores a single rtf download", {
  data <- lint_data(outputs = list(
    log = list(type = "log"),
    a = list(type = "download", format = "rtf")
  ))
  program <- "proc print data=sashelp.class; run;"
  expect_false("L004" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L005 flags a missing %macro", {
  data <- lint_data(run = list(entry = "macro", macro = "report"))
  program <- "proc print data=sashelp.class; run;"
  expect_true("L005" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L005 ignores a present %macro", {
  data <- lint_data(run = list(entry = "macro", macro = "report"))
  program <- "%macro report;\nproc print data=sashelp.class; run;\n%mend report;"
  expect_false("L005" %in% lint_codes(sashiny_lint(data, program)))
})

test_that("L001 path uses the input id when the macro name differs", {
  data <- lint_data(inputs = list(
    min_msrp = list(type = "numeric", label = "Min MSRP", macro = "MSRP")
  ))
  program <- "%let MSRP = 5;\nproc print data=sashelp.class; run;"
  issues <- sashiny_lint(data, program)
  l001 <- Filter(function(i) i$code == "L001", issues)
  expect_length(l001, 1L)
  expect_identical(l001[[1]]$path, "/inputs/min_msrp")
})

test_that("L001 dedupes a daterange's two macro names", {
  data <- lint_data(inputs = list(
    period = list(type = "daterange", label = "Period", macro = list("start_dt", "end_dt"))
  ))
  program <- "%let START_DT = 1;\n%let END_DT = 2;\nproc print data=sashelp.class; run;"
  issues <- sashiny_lint(data, program)
  l001 <- Filter(function(i) i$code == "L001", issues)
  expect_length(l001, 1L)
  expect_identical(l001[[1]]$path, "/inputs/period")
})