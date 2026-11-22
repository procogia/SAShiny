# Package and spec version information (spec section 11).

# The spec release this package implements (spec/CONTRACT.md, section 11).
# CI (spec/tools/check_versions.py) fails when it differs from the spec or
# from the Python library.
.sashiny_spec_release <- "1.7"

#' Package and spec versions
#'
#' Reports the 'SAShiny' version, the release of the contract specification it
#' implements and the contract version it reads (`sashiny: 1`). The R package
#' and the Python library are released together with the same version, and
#' both report the same spec release.
#'
#' @return A `sashiny_info` list with `package`, `version`, `spec` and
#'   `contract`, printed as one line.
#' @examples
#' sas_info()
#' sas_info()$spec
#' @export
sas_info <- function() {
  structure(list(
    package = "SAShiny",
    version = as.character(utils::packageVersion("SAShiny")),
    spec = .sashiny_spec_release,
    contract = 1L
  ), class = "sashiny_info")
}

#' @export
format.sashiny_info <- function(x, ...) {
  sprintf("%s %s (spec %s, contract sashiny: %d)", x$package, x$version, x$spec, x$contract)
}

#' @export
print.sashiny_info <- function(x, ...) {
  cat(format(x), "\n", sep = "")
  invisible(x)
}