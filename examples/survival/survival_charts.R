# SAShiny chart render callback for the survival example (spec 8.5).
#
# The declarative chart spec draws points, lines, bars, histograms and boxes. A
# forest plot also needs confidence-interval bars, a log axis, a reference line
# at HR = 1 and the model's term order, so the demo app draws it with this
# callback instead:
#
#   source("survival_charts.R")
#   sas_program_server("survival", contract, engine,
#                      render = list(forest_plot = forest_chart))
#
# Without the callback the contract's declarative spec is the fallback:
# hazard ratios as points. Needs ggplot2.

forest_chart <- function(value, spec, ...) {
  .data <- ggplot2::.data
  cols <- value$columns
  names <- tolower(vapply(cols, function(col) col$name, character(1)))
  column <- function(name) {
    i <- match(name, names)
    if (is.na(i)) return(rep(NA, length(value$rows)))
    unlist(lapply(value$rows, function(row) if (is.null(row[[i]])) NA else row[[i]]))
  }
  df <- data.frame(
    term = as.character(column("term")),
    hr = suppressWarnings(as.numeric(column("hazard_ratio"))),
    lower = suppressWarnings(as.numeric(column("hr_lower"))),
    upper = suppressWarnings(as.numeric(column("hr_upper"))),
    hr_ci = as.character(column("hr_ci")),
    stringsAsFactors = FALSE
  )
  df <- df[!is.na(df$hr) & df$hr > 0, , drop = FALSE]
  if (nrow(df) == 0L) stop("no hazard ratios to plot")
  df$lower[is.na(df$lower)] <- df$hr[is.na(df$lower)]
  df$upper[is.na(df$upper)] <- df$hr[is.na(df$upper)]
  df$hr_ci[is.na(df$hr_ci)] <- sprintf("%.2f", df$hr[is.na(df$hr_ci)])
  # First model term on top, as in the SAS graph.
  df$pos <- rev(seq_len(nrow(df)))
  i <- match("hr_ci", names)
  label <- if (is.na(i)) NULL else cols[[i]]$label
  header <- if (is.null(label) || !nzchar(label)) "HR (CI)" else label

  lo <- min(df$lower, 1) / 1.15
  hi <- max(df$upper, 1) * 1.15
  df$text_x <- hi * 1.1
  xmax <- hi * 1.1 * (hi / lo)^0.5 # room for the HR (CI) column on the log axis
  breaks <- c(0.05, 0.1, 0.2, 0.25, 0.5, 0.75, 1, 1.5, 2, 3, 4, 5, 10, 20)
  breaks <- breaks[breaks >= lo & breaks <= hi]

  ggplot2::ggplot(df) +
    ggplot2::geom_vline(xintercept = 1, linetype = "dashed", colour = "#888888") +
    ggplot2::geom_segment(
      ggplot2::aes(x = .data$lower, xend = .data$upper, y = .data$pos, yend = .data$pos),
      colour = "#c0504d", linewidth = 0.8
    ) +
    ggplot2::geom_point(ggplot2::aes(x = .data$hr, y = .data$pos),
      shape = 15, size = 3, colour = "#1f3c88"
    ) +
    ggplot2::geom_text(ggplot2::aes(x = .data$text_x, y = .data$pos, label = .data$hr_ci),
      hjust = 0, size = 3.2
    ) +
    ggplot2::annotate("text",
      x = hi * 1.1, y = nrow(df) + 0.6, label = header,
      hjust = 0, size = 3.2, fontface = "bold"
    ) +
    ggplot2::scale_x_log10(breaks = breaks, labels = as.character(breaks), limits = c(lo, xmax)) +
    ggplot2::scale_y_continuous(
      breaks = df$pos, labels = df$term, limits = c(0.5, nrow(df) + 0.8)
    ) +
    ggplot2::labs(
      x = "Hazard ratio (log scale)", y = NULL,
      caption = "Hazard ratio < 1: lower hazard of progression or death than the reference."
    ) +
    ggplot2::theme_bw() +
    ggplot2::theme(panel.grid.minor = ggplot2::element_blank(),
                   panel.grid.major.y = ggplot2::element_blank())
}
