# Internal utilities for SAShiny.

#' Null-coalescing operator
#'
#' Returns `x` unless it is `NULL`, in which case returns `y`.
#'
#' @param x A value.
#' @param y A fallback value.
#' @return `x` if not `NULL`, otherwise `y`.
#' @noRd
`%||%` <- function(x, y) {
  if (is.null(x)) y else x
}