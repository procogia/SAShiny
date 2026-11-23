# The survival example's forest-plot render callback (spec section 8.5).
#
# The callback lives in examples/survival/survival_charts.R, outside the package
# and the cross-language fixtures, so these tests skip when examples/ is absent
# (as under R CMD check). Python/tests/test_survival_charts.py checks the
# plotnine twin against the same value and the same expected layout.

survival_charts_env <- function() {
  path <- normalizePath(
    file.path("..", "..", "..", "examples", "survival", "survival_charts.R"),
    mustWork = FALSE
  )
  if (!file.exists(path)) skip("examples/survival is not available")
  skip_if_not_installed("ggplot2")
  env <- new.env()
  sys.source(path, envir = env)
  env
}

survival_col <- function(name, type = "numeric", label = "") {
  list(name = name, type = type, label = label, format = "")
}

# The shape of work.cox_estimates as collected (upper-case SAS names), with one
# row that must be dropped (no hazard ratio).
survival_value <- list(
  columns = list(
    survival_col("TERM", "character"),
    survival_col("HAZARD_RATIO"),
    survival_col("HR_LOWER"),
    survival_col("HR_UPPER"),
    survival_col("HR_CI", "character", "HR (95% CI)")
  ),
  rows = list(
    list("RX-101 vs Control", 0.82, 0.67, 0.99, "0.82 (0.67, 0.99)"),
    list("Age (per year)", 1.01, 1.00, 1.02, "1.01 (1.00, 1.02)"),
    list("Stage III vs I", NULL, NULL, NULL, NULL),
    list("Male vs Female", 1.2, 0.95, 1.5, "1.20 (0.95, 1.50)")
  ),
  formatted = FALSE
)
survival_terms <- c("RX-101 vs Control", "Age (per year)", "Male vs Female")

test_that("the forest plot keeps the model order, drops missing rows and uses the fixed layout", {
  env <- survival_charts_env()
  p <- env$forest_chart(survival_value, NULL)
  expect_s3_class(p, "ggplot")
  x <- p$scales$get_scales("x")
  y <- p$scales$get_scales("y")
  # lo = 0.67 / 1.15 and hi = 1.5 * 1.15: the breaks inside [lo, hi].
  expect_equal(as.numeric(x$breaks), c(0.75, 1, 1.5))
  expect_equal(as.character(y$labels), survival_terms)
  expect_equal(as.numeric(y$breaks), c(3, 2, 1))
  geoms <- vapply(p$layers, function(l) class(l$geom)[1], character(1), USE.NAMES = FALSE)
  expect_equal(geoms, c("GeomVline", "GeomSegment", "GeomPoint", "GeomText", "GeomText"))
  expect_equal(p$layers[[5]]$aes_params$label, "HR (95% CI)")
  expect_no_error(ggplot2::ggplot_build(p))
})

test_that("the forest plot fills a missing CI column and rejects no hazard ratios", {
  env <- survival_charts_env()
  value <- list(
    columns = list(survival_col("term", "character"), survival_col("hazard_ratio"),
                   survival_col("hr_lower"), survival_col("hr_upper")),
    rows = list(list("a", 0.5, 0.4, 0.6))
  )
  p <- env$forest_chart(value, NULL)
  expect_equal(p$data$hr_ci, "0.50")
  value$rows <- list(list("a", NULL, NULL, NULL), list("b", 0, 0, 0))
  expect_error(env$forest_chart(value, NULL), "no hazard ratios")
})
