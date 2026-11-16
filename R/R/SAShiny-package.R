#' SAShiny: use unchanged SAS programs as the server of Shiny applications
#'
#' A SAShiny app pairs an unmodified 'SAS' program with a YAML contract
#' ([sas_contract()]) and runs it on a live 'SAS' system ([sas_connect()]).
#'
#' @section Supported systems and licensing:
#' Programs run only on 'SAS' 9.4, 'SAS Viya' or 'SAS OnDemand for Academics'.
#' Users are responsible for holding a valid licence for the system they
#' connect to, and must acknowledge this before a run (`license_ack = TRUE`,
#' `options(SAShiny.license_ack = TRUE)` or `SASHINY_LICENSE_ACK=true`).
#'
#' @section Options:
#' * `SAShiny.license_ack`: `TRUE` acknowledges licence responsibility for
#'   every engine in the session that does not set `license_ack` itself.
#'
#' @keywords internal
"_PACKAGE"

## usethis namespace: start
## usethis namespace: end
NULL
