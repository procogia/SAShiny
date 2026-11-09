# Advisory lint for SAShiny (spec section 10).
#
# Reports program-vs-contract consistency findings (L001-L005). These are
# advisory, not errors. The full implementation scans the SAS program text;
# this module currently provides the interface and will be completed in a
# later phase.

#' Lint a contract against its program text
#'
#' Returns advisory findings (L001-L005). Currently a stub returning no
#' findings; the full implementation will scan the SAS program text.
#'
#' @param data The parsed contract data (a list).
#' @param program_text The decoded SAS program text.
#' @return A list of `sashiny_issue` objects with `L0xx` codes.
#' @export
sashiny_lint <- function(data, program_text) {
  list()
}