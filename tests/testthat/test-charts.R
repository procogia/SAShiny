# Tests for the client-side chart rendering engine (spec section 8.5).

test_that("chart backends report availability", {
  backends <- sas_chart_backends()
  expect_true(all(c("ggplot2", "plotly", "base") %in% names(backends)))
  expect_true(backends[["base"]])
})

test_that("render_chart requires a spec or callback", {
  value <- list(
    columns = list(
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4)),
    total_rows = 2L, truncated = FALSE, formatted = FALSE
  )
  expect_error(sas_render_chart(value, NULL, backend = "base"), "no spec and no render")
})

test_that("render_chart rejects an unknown backend", {
  value <- list(
    columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE
  )
  expect_error(
    sas_render_chart(value, list(kind = "scatter", x = "x"), backend = "nope"),
    "unknown chart backend"
  )
})

test_that("render_chart rejects an unknown column", {
  value <- list(
    columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE
  )
  expect_error(
    sas_render_chart(value, list(kind = "scatter", x = "nope"), backend = "base"),
    "unknown column"
  )
})

test_that("render_chart rejects an unknown kind", {
  value <- list(
    columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE
  )
  expect_error(
    sas_render_chart(value, list(kind = "pie", x = "x"), backend = "base"),
    "unknown chart kind"
  )
})

test_that("render_chart callback takes precedence", {
  value <- list(
    columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE
  )
  out <- sas_render_chart(
    value, list(kind = "scatter", x = "x"),
    backend = "base", render = function(v, s) "custom"
  )
  expect_identical(out, "custom")
})

test_that("base backend renders a scatter plot to a recorded plot", {
  value <- list(
    columns = list(
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4), list(3, 6)),
    total_rows = 3L, truncated = FALSE, formatted = FALSE
  )
  plot <- sas_render_chart(value, list(kind = "scatter", x = "x", y = "y"), backend = "base")
  expect_s3_class(plot, "recordedplot")
})
# A chart value as collected from SAS: upper-case column names, a SAS label,
# a character column and (in chart_value_missing) a SAS missing value.
chart_value <- function() {
  list(
    columns = list(
      list(name = "Height", type = "numeric", label = "Height (in)", format = ""),
      list(name = "Weight", type = "numeric", label = "", format = ""),
      list(name = "Sex", type = "character", label = "", format = "")
    ),
    rows = list(
      list(51.3, 50.5, "M"), list(56.5, 84, "F"), list(62.8, 102.5, "F"),
      list(69, 112.5, "M"), list(57.3, 83, "F"), list(63.5, 102.5, "M")
    ),
    total_rows = 6L, truncated = FALSE, formatted = FALSE
  )
}

chart_spec <- function(kind, ...) {
  utils::modifyList(
    list(kind = kind, x = if (kind == "box") "sex" else "height", y = "weight"),
    list(...)
  )
}

chart_kinds <- c("scatter", "line", "bar", "histogram", "box")

test_that("a chart value becomes a typed data frame", {
  value <- chart_value()
  value$rows[[2]] <- list(56.5, NULL, "F")
  df <- SAShiny:::.sashiny_chart_frame(value)
  expect_identical(names(df), c("Height", "Weight", "Sex"))
  expect_type(df$Height, "double")
  expect_type(df$Sex, "character")
  expect_true(is.na(df$Weight[[2]]))
  expect_identical(nrow(df), 6L)

  formatted <- chart_value()
  formatted$formatted <- TRUE
  formatted$rows <- lapply(formatted$rows, function(r) lapply(r, as.character))
  expect_type(SAShiny:::.sashiny_chart_frame(formatted)$Height, "character")

  empty <- chart_value()
  empty$rows <- list()
  expect_identical(nrow(SAShiny:::.sashiny_chart_frame(empty)), 0L)
})

test_that("spec columns resolve case-insensitively to the collected names", {
  spec <- SAShiny:::.sashiny_chart_resolve(
    chart_value(),
    list(kind = "scatter", x = "HEIGHT", y = "weight", color = "sex", facet = "Sex")
  )
  expect_identical(
    spec[c("x", "y", "color", "facet")],
    list(x = "Height", y = "Weight", color = "Sex", facet = "Sex")
  )
  expect_error(
    SAShiny:::.sashiny_chart_resolve(chart_value(), list(kind = "line", x = "height")),
    "chart kind 'line' requires a 'y' column"
  )
  hist <- list(kind = "histogram", x = "height", y = "weight")
  expect_null(SAShiny:::.sashiny_chart_resolve(chart_value(), hist)$y)
  bad <- list(kind = "scatter", x = "height", color = "nope")
  expect_error(
    SAShiny:::.sashiny_chart_resolve(chart_value(), bad),
    "unknown column 'nope'"
  )
})

test_that("the ggplot2 backend builds every chart kind", {
  skip_if_not_installed("ggplot2")
  for (kind in chart_kinds) {
    spec <- chart_spec(kind, color = "SEX", title = "T")
    plot <- sas_render_chart(chart_value(), spec, backend = "ggplot2")
    expect_s3_class(plot, "ggplot")
    expect_no_error(ggplot2::ggplot_build(plot))
    png <- SAShiny:::.sashiny_plot_png(plot)
    expect_gt(nchar(png), 1000)
  }
  spec <- chart_spec("scatter", facet = "sex")
  faceted <- sas_render_chart(chart_value(), spec, backend = "ggplot2")
  expect_no_error(ggplot2::ggplot_build(faceted))
})

test_that("the plotly backend builds every chart kind", {
  skip_if_not_installed("plotly")
  for (kind in chart_kinds) {
    spec <- chart_spec(kind, color = "sex", title = "T")
    plot <- sas_render_chart(chart_value(), spec, backend = "plotly")
    expect_s3_class(plot, "plotly")
    expect_no_error(plotly::plotly_build(plot))
  }
})

test_that("the base backend draws every chart kind to a PNG, headless", {
  before <- grDevices::dev.list()
  for (kind in chart_kinds) {
    plot <- sas_render_chart(chart_value(), chart_spec(kind, title = "T"), backend = "base")
    expect_s3_class(plot, "recordedplot")
    png <- SAShiny:::.sashiny_plot_png(plot)
    expect_gt(nchar(png), 1000)
  }
  # Rendering opens and closes its own devices only.
  expect_identical(grDevices::dev.list(), before)
})

test_that("the module shows charts as images or interactive widgets", {
  skip_if_not_installed("shiny")
  value <- chart_value()
  base <- SAShiny:::.sashiny_chart_tag(value, list(spec = chart_spec("scatter", backend = "base")))
  expect_match(as.character(base), "data:image/png;base64,", fixed = TRUE)

  skip_if_not_installed("ggplot2")
  default <- SAShiny:::.sashiny_chart_tag(value, list(spec = chart_spec("scatter")))
  expect_match(as.character(default), "data:image/png;base64,", fixed = TRUE)

  skip_if_not_installed("plotly")
  spec <- chart_spec("scatter", backend = "plotly")
  widget <- SAShiny:::.sashiny_chart_tag(value, list(spec = spec))
  expect_true(inherits(widget[[1]], "plotly"))
})

test_that("the module says why a chart could not be rendered", {
  skip_if_not_installed("shiny")
  expect_message(
    tag <- SAShiny:::.sashiny_chart_tag(
      chart_value(),
      list(spec = list(kind = "scatter", x = "nope", y = "weight", backend = "base"))
    ),
    "unknown column 'nope'"
  )
  expect_match(
    as.character(tag), "Could not render this chart: unknown column 'nope'",
    fixed = TRUE
  )
})
