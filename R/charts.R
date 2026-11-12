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

#' The chart kinds of spec section 8.5
#' @noRd
.sashiny_chart_kinds <- c("scatter", "line", "bar", "histogram", "box")

#' The spec fields that name a column (spec section 8.5)
#' @noRd
.sashiny_chart_fields <- c("x", "y", "color", "fill", "facet")

#' Validate a chart spec and resolve its column names
#'
#' Checks the kind, then replaces each column field (`x`, `y`, `color`,
#' `fill`, `facet`) with the collected column's own name, matched
#' case-insensitively (spec section 8.5). An unknown column is an error, as is
#' a missing `y` for every kind except `histogram`, which ignores `y`.
#' @noRd
.sashiny_chart_resolve <- function(value, spec) {
  kind <- spec$kind %||% ""
  if (!kind %in% .sashiny_chart_kinds) {
    stop(sprintf("unknown chart kind '%s'", kind), call. = FALSE)
  }
  for (field in .sashiny_chart_fields) {
    if (!is.null(spec[[field]])) {
      spec[[field]] <- value$columns[[.sashiny_chart_col(value, spec[[field]])]]$name
    }
  }
  if (kind == "histogram") {
    spec$y <- NULL
  } else if (is.null(spec$y)) {
    stop(sprintf("chart kind '%s' requires a 'y' column", kind), call. = FALSE)
  }
  spec
}

#' A chart value as a data frame
#'
#' One column per collected column, in order and under its own name. Numeric
#' columns of an unformatted value become numeric vectors with SAS missing
#' (`NULL`) as `NA`; every other column becomes a character vector.
#' @noRd
.sashiny_chart_frame <- function(value) {
  cols <- value$columns %||% list()
  rows <- value$rows %||% list()
  numeric_ok <- !isTRUE(value$formatted)
  out <- lapply(seq_along(cols), function(i) {
    cells <- lapply(rows, function(row) {
      cell <- row[[i]]
      if (is.null(cell)) NA else cell
    })
    cells <- unlist(cells, use.names = FALSE)
    if (is.null(cells)) cells <- logical(0)
    if (numeric_ok && identical(cols[[i]]$type, "numeric")) {
      suppressWarnings(as.numeric(cells))
    } else {
      as.character(cells)
    }
  })
  names(out) <- vapply(cols, function(col) col$name, character(1))
  as.data.frame(out, stringsAsFactors = FALSE, check.names = FALSE, optional = TRUE)
}

#' Render a chart value to a plot object
#'
#' @param value The collected chart value (spec section 8.1 table shape).
#' @param spec The declarative chart spec (spec section 8.5), or NULL.
#' @param backend One of `"ggplot2"`, `"base"` or `"plotly"`.
#' @param render An optional user callback `function(value, spec, ...)` that
#'   takes precedence over the declarative spec.
#' @return A plot object for the chosen backend: a `ggplot`, a
#'   `recordedplot` (base graphics) or a `plotly` htmlwidget.
#' @export
sas_render_chart <- function(value, spec = NULL, backend = "ggplot2", render = NULL) {
  if (!is.null(render)) {
    return(render(value, spec))
  }
  if (is.null(spec)) {
    stop("chart has no spec and no render callback", call. = FALSE)
  }
  if (!backend %in% c("ggplot2", "base", "plotly")) {
    stop(sprintf("unknown chart backend '%s'", backend), call. = FALSE)
  }
  spec <- .sashiny_chart_resolve(value, spec)
  switch(backend,
    ggplot2 = .sashiny_chart_ggplot2(value, spec),
    base = .sashiny_chart_base(value, spec),
    plotly = .sashiny_chart_plotly(value, spec)
  )
}

#' Which optional chart backends are installed
#' @return A named logical vector: `ggplot2`, `plotly` and `base`.
#' @export
sas_chart_backends <- function() {
  c(
    ggplot2 = requireNamespace("ggplot2", quietly = TRUE),
    plotly = requireNamespace("plotly", quietly = TRUE),
    base = TRUE
  )
}

#' Stop unless an optional backend package is installed
#' @noRd
.sashiny_chart_need <- function(pkg) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    stop(
      sprintf(
        "the '%s' package is needed to render this chart; install it with install.packages(\"%s\")",
        pkg, pkg
      ),
      call. = FALSE
    )
  }
}

#' Render with ggplot2
#' @noRd
.sashiny_chart_ggplot2 <- function(value, spec) {
  .sashiny_chart_need("ggplot2")
  data <- .sashiny_chart_frame(value)
  .data <- ggplot2::.data
  mapping <- ggplot2::aes(x = .data[[spec$x]])
  if (!is.null(spec$y) && spec$kind != "histogram") mapping$y <- ggplot2::aes(y = .data[[spec$y]])$y
  if (!is.null(spec$color)) mapping$colour <- ggplot2::aes(colour = .data[[spec$color]])$colour
  if (!is.null(spec$fill)) mapping$fill <- ggplot2::aes(fill = .data[[spec$fill]])$fill
  plot <- ggplot2::ggplot(data, mapping) + switch(spec$kind,
    scatter = ggplot2::geom_point(),
    line = ggplot2::geom_line(),
    bar = ggplot2::geom_col(),
    histogram = ggplot2::geom_histogram(bins = 30L),
    box = ggplot2::geom_boxplot()
  )
  if (!is.null(spec$facet)) {
    plot <- plot + ggplot2::facet_wrap(ggplot2::vars(.data[[spec$facet]]))
  }
  plot + ggplot2::labs(
    title = spec$title, subtitle = spec$subtitle,
    x = spec$xlab %||% spec$x,
    y = spec$ylab %||% (if (spec$kind == "histogram") NULL else spec$y) %||% ggplot2::waiver()
  )
}

#' Render with base R graphics
#'
#' Draws on a private null device with its display list enabled, so the
#' recorded plot replays on any device. The current device of a headless R
#' session (`pdf`) records nothing, so it is not used.
#' @noRd
.sashiny_chart_base <- function(value, spec) {
  data <- .sashiny_chart_frame(value)
  xs <- data[[spec$x]]
  ys <- if (is.null(spec$y)) NULL else data[[spec$y]]
  xlab <- spec$xlab %||% spec$x
  ylab <- spec$ylab %||% spec$y %||% ""
  previous <- grDevices::dev.cur()
  grDevices::pdf(NULL)
  device <- grDevices::dev.cur()
  on.exit(
    {
      grDevices::dev.off(device)
      if (previous > 1L) grDevices::dev.set(previous)
    },
    add = TRUE
  )
  grDevices::dev.control("enable")
  switch(spec$kind,
    scatter = graphics::plot(xs, ys, xlab = xlab, ylab = ylab),
    line = graphics::plot(xs, ys, type = "l", xlab = xlab, ylab = ylab),
    bar = graphics::barplot(as.numeric(ys), names.arg = xs, xlab = xlab, ylab = ylab),
    histogram = graphics::hist(as.numeric(xs), main = "", xlab = xlab),
    box = if (is.null(ys)) {
      graphics::boxplot(as.numeric(xs), xlab = xlab)
    } else {
      graphics::boxplot(as.numeric(ys) ~ xs, xlab = xlab, ylab = ylab)
    }
  )
  graphics::title(main = spec$title %||% "", sub = spec$subtitle %||% "")
  grDevices::recordPlot()
}

#' Render with plotly
#' @noRd
.sashiny_chart_plotly <- function(value, spec) {
  .sashiny_chart_need("plotly")
  data <- .sashiny_chart_frame(value)
  col <- function(name) stats::as.formula(paste0("~`", name, "`"))
  args <- list(data, x = col(spec$x))
  if (!is.null(spec$y) && spec$kind != "histogram") args$y <- col(spec$y)
  if (!is.null(spec$color)) args$color <- col(spec$color)
  args <- c(args, switch(spec$kind,
    scatter = list(type = "scatter", mode = "markers"),
    line = list(type = "scatter", mode = "lines"),
    bar = list(type = "bar"),
    histogram = list(type = "histogram"),
    box = list(type = "box")
  ))
  fig <- do.call(plotly::plot_ly, args)
  plotly::layout(fig,
    title = spec$title %||% "",
    xaxis = list(title = spec$xlab %||% spec$x),
    yaxis = list(title = spec$ylab %||% (if (spec$kind == "histogram") NULL else spec$y) %||% "")
  )
}
