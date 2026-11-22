# R/Python parity (docs/parity.md). Each test pins a behaviour the Python
# library shares; the Python counterparts are in Python/tests/test_parity.py.
# The cross-language cases (values, log scope) are shared
# fixtures under spec/fixtures.

stamp_re <- "^\\d{4}-\\d\\d-\\d\\dT\\d\\d:\\d\\d:\\d\\dZ$"

parity_contract <- function(name) {
  sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", name, "contract.sashiny.yml"))
}

write_contract <- function(text) {
  dir <- withr::local_tempdir(.local_envir = parent.frame())
  writeLines("data _null_; run;", file.path(dir, "program.sas"))
  path <- file.path(dir, "c.sashiny.yml")
  writeLines(text, path)
  path
}

test_that("default module ids split both separators and strip every combining mark", {
  expect_identical(.sashiny_default_module_id("C:\\progs\\Cars.sas"), "cars")
  expect_identical(.sashiny_default_module_id("dir/sub\\Cars.sas"), "cars")
  # U+093F (Devanagari vowel sign I, category Mc) is a combining mark too.
  expect_identical(.sashiny_default_module_id("a\u093fb.sas"), "ab")
})

test_that("S013: the program must be a file, not a directory", {
  path <- write_contract(c(
    "sashiny: 1", "program: sub.sas", "title: T", "outputs:", "  log:", "    type: log"
  ))
  dir.create(file.path(dirname(path), "sub.sas"))
  issues <- sas_validate(sas_contract(path))
  expect_true("S013" %in% vapply(issues, function(i) i$code, ""))
})

test_that("sas_check() reasons have no double space (#153)", {
  bad <- .sashiny_result("r", "error", metadata = list(
    issues = list(list(code = "V014", input = "", message = "no column AGE"))
  ))
  e <- tryCatch(sas_check(bad), error = function(e) e)
  expect_match(conditionMessage(e), "invalid input V014 no column AGE", fixed = TRUE)
})

test_that("table label and format are ASCII-trimmed, missing is empty", {
  meta <- list(
    list(name = "a", type = "numeric", label = "  Age \f", format = NA),
    list(name = "b", type = "character", label = NULL, format = " $8. ")
  )
  value <- .sashiny_build_table(meta, list(list(1, "x")),
    total_rows = 1L, max_rows = 10L, formatted = FALSE
  )
  got <- lapply(value$columns, function(c) c(c$label, c$format))
  expect_identical(got, list(c("Age", ""), c("", "$8.")))
})

test_that("run metadata uses whole-second UTC stamps (spec section 8.4)", {
  result <- sas_run(parity_contract("minimal"), .sashiny_engine_mock(), list(),
    today = .sashiny_today
  )
  expect_match(result$metadata$started_at, stamp_re, perl = TRUE)
  expect_match(result$metadata$ended_at, stamp_re, perl = TRUE)
  expect_identical(result$metadata$engine_version, as.character(utils::packageVersion("SAShiny")))
})

test_that("a licence refusal reports the package version, as in Python", {
  engine <- test_saspy_engine(license_ack = FALSE)
  withr::local_envvar(SASHINY_LICENSE_ACK = NA)
  withr::local_options(SAShiny.license_ack = NULL)
  result <- sas_engine_run(engine, parity_contract("minimal"), list(), today = .sashiny_today)
  expect_match(result$metadata$engine_error, "^SAS licence not acknowledged")
  expect_identical(result$metadata$engine_version, as.character(utils::packageVersion("SAShiny")))
})

test_that("sas_oda() rejects an unknown region with a SAShiny engine error", {
  expect_error(sas_oda("xx9"), "unknown ODA region xx9", class = "sashiny_error_engine")
  expect_identical(sas_oda()$cfg$iomhost, .sashiny_oda_hosts[["us1"]])
})

test_that("pool choices on a closed pool raise 'pool closed'", {
  pool <- sas_pool(.sashiny_engine_mock(), max_size = 1L)
  sas_close(pool)
  expect_error(sas_engine_choices(pool, parity_contract("minimal")), "pool closed",
    class = "sashiny_error_engine"
  )
})

test_that("the result cache store can be replaced (spec section 6.11)", {
  previous <- sas_cache_set_store(sas_cache_lru(max_entries = 2L))
  withr::defer(sas_cache_set_store(previous))
  store <- sas_cache_store()
  store$set("k", .sashiny_result("r", "success"), 1)
  expect_identical(store$get("k")$stored_at, 1)
  sas_cache_clear()
  expect_null(store$get("k"))
  expect_error(sas_cache_set_store(list(get = identity)), "get, set, delete and clear",
    class = "sashiny_error_engine"
  )
})

chart_value <- function() {
  list(
    columns = list(
      list(name = "g", type = "character", label = "", format = ""),
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list("a", 1, 2), list("b", 2, 3)),
    total_rows = 2L, truncated = FALSE, formatted = FALSE
  )
}

test_that("base graphics refuse mappings they cannot draw (spec section 8.5)", {
  cases <- list(
    list(spec = list(kind = "scatter", x = "x", y = "y", fill = "g"), msg = "fill for kind scatter"),
    list(spec = list(kind = "bar", x = "g", y = "y", color = "g"), msg = "color for kind bar"),
    list(spec = list(kind = "histogram", x = "x", color = "g"), msg = "color for kind histogram"),
    list(spec = list(kind = "box", x = "g", y = "y", color = "x"), msg = "color for kind box")
  )
  for (case in cases) {
    expect_error(sas_render_chart(chart_value(), case$spec, backend = "base"),
      paste("chart backend base cannot map", case$msg),
      class = "sashiny_error_values"
    )
  }
  # A box plot coloured by its own x groups honours both mappings.
  plot <- sas_render_chart(chart_value(), list(kind = "box", x = "g", y = "y", color = "g"),
    backend = "base"
  )
  expect_s3_class(plot, "recordedplot")
})

test_that("plotly refuses color and fill together, and shows the subtitle", {
  skip_if_not_installed("plotly")
  expect_error(
    sas_render_chart(chart_value(), list(kind = "bar", x = "g", y = "y", color = "g", fill = "g"),
      backend = "plotly"
    ),
    "cannot map both color and fill",
    class = "sashiny_error_values"
  )
  fig <- sas_render_chart(chart_value(),
    list(kind = "scatter", x = "x", y = "y", title = "T", subtitle = "S"),
    backend = "plotly"
  )
  built <- plotly::plotly_build(fig)
  title <- built$x$layout$title
  expect_identical(if (is.list(title)) title$text else title, "T<br><sup>S</sup>")
})

test_that("upload fixtures read the same in both languages (spec section 7)", {
  skip_if_not_installed("openxlsx")
  for (name in c("character_cells", "xlsx_reading")) {
    folder <- file.path(.sashiny_fixtures(), "uploads", name)
    case <- jsonlite::fromJSON(file.path(folder, "case.json"), simplifyVector = FALSE)
    spec <- list(
      type = "dataset", label = "Cells", target = "work.cells", accept = list("xlsx"),
      columns = lapply(case$columns, function(c) list(name = c, type = "character"))
    )
    path <- file.path(folder, case$file)
    read <- .sashiny_read_upload(.sashiny_upload_file(path), spec)
    got <- lapply(stats::setNames(nm = unlist(case$columns)), function(c) read$df[[c]])
    expect_identical(got, lapply(case$expected, unlist), label = name)
  }
})
