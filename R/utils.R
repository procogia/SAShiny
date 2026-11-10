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

#' Stop with a clear message when a suggested package is missing.
#'
#' @param pkg The package name.
#' @param reason Why it is needed, e.g. `"to read xlsx uploads"`.
#' @noRd
.sashiny_need <- function(pkg, reason) {
  if (!requireNamespace(pkg, quietly = TRUE)) {
    message <- sprintf(
      "The '%s' package is required %s. Install it with install.packages(\"%s\").",
      pkg, reason, pkg
    )
    stop(message, call. = FALSE)
  }
  invisible(TRUE)
}

#' UTC timestamp in ISO 8601.
#' @noRd
.sashiny_now <- function() {
  format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

#' Read a whole file as raw bytes.
#' @noRd
.sashiny_read_bytes <- function(path) {
  readBin(path, "raw", n = file.info(path)$size)
}

#' Base64 text of raw bytes, without line breaks.
#' @noRd
.sashiny_b64enc <- function(bytes) {
  openssl::base64_encode(bytes, linebreaks = FALSE)
}
