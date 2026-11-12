# Client-side chart rendering for SAShiny.
#
# A `chart` output carries the collected data (the same shape as a `table`
# value, spec section 8.1) and is rendered by the Shiny module, not by SAS.
# This file turns that data plus a declarative `spec` (spec section 8.5) into a
# plot object for one of three optional backends: ggplot2, base R graphics or
# plotly. The backends are optional dependencies; each is loaded lazily.

#' Column index of a chart value, matched case-insensitively
#' @noRd
.sashiny_chart_col <- function(value, name) {
  cols <- value$columns %||% list()
  for (i in seq_along(cols)) {
    if (tolower(cols[[i]]$name) == tolower(name)) {
      return(i)
    }
  }
  stop(sprintf("unknown column '%s'", name), call. = FALSE)
}

#' Column values of a chart value
#' @noRd
.sashiny_chart_series <- function(value, name) {
  i <- .sashiny_chart_col(value, name)
  lapply(value$rows %||% list(), function(row) row[[i]])
}

#' Column label of a chart value
#' @noRd
.sashiny_chart_label <- function(value, name) {
  i <- .sashiny_chart_col(value, name)
  col <- value$columns[[i]]
  if (is.null(col$label) || !nzchar(col$label)) col$name else col$label
}

#' Render a chart value to a plot object
#'
#' @param value The collected chart value (spec section 8.1 table shape).
#' @param spec The declarative chart spec (spec section 8.5), or NULL.
#' @param backend One of `"ggplot2"`, `"base"` or `"plotly"`.
#' @param render An optional user callback `function(value, spec, ...)` that
#'   takes precedence over the declarative spec.
#' @return A plot object for the chosen backend.
#' @export
sas_render_chart <- function(value, spec = NULL, backend = "ggplot2", render = NULL) {
  if (!is.null(render)) {
    return(render(value, spec))
  }
  if (is.null(spec)) {
    stop("chart has no spec and no render callback", call. = FALSE)
  }
  if (identical(backend, "ggplot2")) {
    return(.sashiny_chart_ggplot2(value, spec))
  }
  if (identical(backend, "base")) {
    return(.sashiny_chart_base(value, spec))
  }
  if (identical(backend, "plotly")) {
    return(.sashiny_chart_plotly(value, spec))
  }
  stop(sprintf("unknown chart backend '%s'", backend), call. = FALSE)
}

#' Which optional chart backends are installed
#' @export
sas_chart_backends <- function() {
  c(
    ggplot2 = requireNamespace("ggplot2", quietly = TRUE),
    plotly = requireNamespace("plotly", quietly = TRUE),
    base = TRUE
  )
}

#' Render with ggplot2
#' @noRd
.sashiny_chart_ggplot2 <- function(value, spec) {
  rlang::check_installed("ggplot2", reason = "to render charts with ggplot2")
  kind <- spec$kind
  x <- spec$x
  y <- spec$y
  mapping <- ggplot2::aes(x = rlang::.data[[x]])
  if (!is.null(y)) {
    mapping <- ggplot2::aes(x = rlang::.data[[x]], y = rlang::.data[[y]])
  }
  if (!is.null(spec$color)) {
    mapping$colour <- rlang::sym(spec$color)
  }
  if (!is.null(spec$fill)) {
    mapping$fill <- rlang::sym(spec$fill)
  }
  plot <- ggplot2::ggplot(value, mapping)
  plot <- plot + switch(kind,
    scatter = ggplot2::geom_point(),
    line = ggplot2::geom_line(),
    bar = ggplot2::geom_bar(stat = "identity"),
    histogram = ggplot2::geom_histogram(),
    box = ggplot2::geom_boxplot(),
    stop(sprintf("unknown chart kind '%s'", kind), call. = FALSE)
  )
  if (!is.null(spec$facet)) {
    plot <- plot + ggplot2::facet_wrap(stats::as.formula(paste0("~", spec$facet)))
  }
  labels <- list()
  if (!is.null(spec$title)) labels$title <- spec$title
  if (!is.null(spec$subtitle)) labels$subtitle <- spec$subtitle
  if (!is.null(spec$xlab)) labels$x <- spec$xlab
  if (!is.null(spec$ylab)) labels$y <- spec$ylab
  if (length(labels)) {
    plot <- plot + do.call(ggplot2::labs, labels)
  }
  plot
}

#' Render with base R graphics
#' @noRd
.sashiny_chart_base <- function(value, spec) {
  kind <- spec$kind
  x <- spec$x
  y <- spec$y
  xs <- unlist(.sashiny_chart_series(value, x), use.names = FALSE)
  ys <- if (is.null(y)) NULL else unlist(.sashiny_chart_series(value, y), use.names = FALSE)
  switch(kind,
    scatter = graphics::plot(xs, ys),
    line = graphics::plot(xs, ys, type = "l"),
    bar = graphics::barplot(as.numeric(ys), names.arg = xs),
    histogram = graphics::hist(as.numeric(xs)),
    box = graphics::boxplot(as.numeric(ys)),
    stop(sprintf("unknown chart kind '%s'", kind), call. = FALSE)
  )
  if (!is.null(spec$title)) {
    graphics::title(main = spec$title)
  }
  invisible(grDevices::recordPlot())
}

#' Render with plotly
#' @noRd
.sashiny_chart_plotly <- function(value, spec) {
  rlang::check_installed("plotly", reason = "to render charts with plotly")
  kind <- spec$kind
  x <- spec$x
  y <- spec$y
  color <- spec$color
  fig <- switch(kind,
    scatter = plotly::plot_ly(value, x = ~.data[[x]], y = ~.data[[y]], color = color, type = "scatter", mode = "markers"),
    line = plotly::plot_ly(value, x = ~.data[[x]], y = ~.data[[y]], color = color, type = "scatter", mode = "lines"),
    bar = plotly::plot_ly(value, x = ~.data[[x]], y = ~.data[[y]], color = color, type = "bar"),
    histogram = plotly::plot_ly(value, x = ~.data[[x]], color = color, type = "histogram"),
    box = plotly::plot_ly(value, x = ~.data[[x]], y = ~.data[[y]], color = color, type = "box"),
    stop(sprintf("unknown chart kind '%s'", kind), call. = FALSE)
  )
  if (!is.null(spec$title)) {
    fig <- plotly::layout(fig, title = spec$title)
  }
  fig
}