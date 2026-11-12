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
  value <- list(columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE)
  expect_error(
    sas_render_chart(value, list(kind = "scatter", x = "x"), backend = "nope"),
    "unknown chart backend"
  )
})

test_that("render_chart rejects an unknown column", {
  value <- list(columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE)
  expect_error(
    sas_render_chart(value, list(kind = "scatter", x = "nope"), backend = "base"),
    "unknown column"
  )
})

test_that("render_chart rejects an unknown kind", {
  value <- list(columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE)
  expect_error(
    sas_render_chart(value, list(kind = "pie", x = "x"), backend = "base"),
    "unknown chart kind"
  )
})

test_that("render_chart callback takes precedence", {
  value <- list(columns = list(list(name = "x", type = "numeric", label = "", format = "")),
    rows = list(list(1)), total_rows = 1L, truncated = FALSE, formatted = FALSE)
  out <- sas_render_chart(value, list(kind = "scatter", x = "x"),
    backend = "base", render = function(v, s) "custom")
  expect_identical(out, "custom")
})

test_that("base backend renders a scatter plot to a base64 PNG", {
  value <- list(
    columns = list(
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4), list(3, 6)),
    total_rows = 3L, truncated = FALSE, formatted = FALSE
  )
  png <- sas_render_chart(value, list(kind = "scatter", x = "x", y = "y"), backend = "base")
  expect_type(png, "character")
  expect_true(nzchar(png))
  # The PNG is non-empty and decodes to a valid image.
  bytes <- openssl::base64_decode(png)
  expect_gt(length(bytes), 8L)
  expect_identical(rawToChar(bytes[1:8]), "\x89PNG\r\n\x1a\n")
})

test_that("chart data frame maps spec names to real column names", {
  value <- list(
    columns = list(
      list(name = "Height", type = "numeric", label = "", format = ""),
      list(name = "Weight", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4), list(3, 6)),
    total_rows = 3L, truncated = FALSE, formatted = FALSE
  )
  data <- SAShiny:::.sashiny_chart_data(value)
  expect_identical(names(data), c("Height", "Weight"))
  expect_identical(data$Height, c(1, 2, 3))
  expect_identical(data$Weight, c(2, 4, 6))
})

test_that("ggplot2 backend renders every chart kind", {
  skip_if_not_installed("ggplot2")
  value <- list(
    columns = list(
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4), list(3, 6)),
    total_rows = 3L, truncated = FALSE, formatted = FALSE
  )
  for (kind in c("scatter", "line", "bar", "histogram", "box")) {
    plot <- sas_render_chart(value, list(kind = kind, x = "x", y = "y"), backend = "ggplot2")
    expect_s3_class(plot, "ggplot")
  }
})

test_that("plotly backend renders every chart kind", {
  skip_if_not_installed("plotly")
  value <- list(
    columns = list(
      list(name = "x", type = "numeric", label = "", format = ""),
      list(name = "y", type = "numeric", label = "", format = "")
    ),
    rows = list(list(1, 2), list(2, 4), list(3, 6)),
    total_rows = 3L, truncated = FALSE, formatted = FALSE
  )
  for (kind in c("scatter", "line", "bar", "histogram", "box")) {
    fig <- sas_render_chart(value, list(kind = kind, x = "x", y = "y"), backend = "plotly")
    expect_s3_class(fig, "plotly")
  }
})