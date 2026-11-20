# SAS connection profiles for deployment (spec/CONTRACT.md section 6.8).
#
# A profile names the 'SAS' system a deployed app connects to. Deployment
# targets use it for egress endpoints, the Java requirement and the runtime
# environment variables; `sas_connect_env()` uses those variables inside the
# deployed app to build its engine. Mirrors `sashiny.profiles`.

#' Characters never allowed in a host or URL written to generated files.
#' @noRd
.sashiny_unsafe_value <- "[[:space:][:cntrl:]\"'\\\\$`]"

#' Characters never allowed in a path (spaces are allowed).
#' @noRd
.sashiny_unsafe_path <- "[\t\n\r[:cntrl:]\"'\\\\$`]"

#' Stop with a profile error.
#' @noRd
.sashiny_profile_fail <- function(name, message) {
  .sashiny_abort("deploy", sprintf("profile %s: %s", name, message))
}

#' Check that a profile field is a safe non-empty string.
#' @noRd
.sashiny_profile_safe <- function(name, field, value, path = FALSE) {
  if (!is.character(value) || length(value) != 1L || is.na(value) || !nzchar(value)) {
    .sashiny_profile_fail(name, paste(field, "must be a non-empty string"))
  }
  if (grepl(if (path) .sashiny_unsafe_path else .sashiny_unsafe_value, value)) {
    .sashiny_profile_fail(name, paste(field, "contains characters that are not allowed"))
  }
  value
}

#' Validate a SAS connection profile for deployment
#'
#' Checks a profile (for example one entry of a connections file read with
#' [sas_load_profiles()]) against spec section 6.8 and derives what a
#' deployment target needs: the profile kind, the `host:port` egress endpoints,
#' whether Java 17 is needed, the plain runtime environment variables and the
#' names of the secret variables.
#'
#' @param profile A named list with `method` (`"iom"`, `"http"` or `"ssh"`) and
#'   the fields of that method: `oda_region` for ODA, `iomhost`/`iomport` for
#'   'SAS' 9.4 IOM, `url` for 'SAS Viya', `host`/`saspath` for SSH; optionally
#'   `requires_vpn`.
#' @param name The profile name; defaults to `profile$name`.
#' @return A `sashiny_profile` object: a list with `name`, `method`, `kind`,
#'   `endpoints`, `needs_java`, `requires_vpn`, `env` (a named character vector,
#'   in spec order) and `secrets` (a character vector of names).
#' @examples
#' p <- sas_profile(list(method = "iom", oda_region = "eu1"), name = "oda")
#' p$kind
#' p$endpoints
#' p$env
#' @export
sas_profile <- function(profile, name = NULL) {
  pname <- as.character(name %||% profile$name %||% "profile")
  method <- profile$method
  if (!is.character(method) || length(method) != 1L || !method %in% c("iom", "http", "ssh")) {
    .sashiny_profile_fail(pname, "method must be one of iom, http or ssh")
  }
  vpn <- profile$requires_vpn %||% FALSE
  if (!is.logical(vpn) || length(vpn) != 1L || is.na(vpn)) {
    .sashiny_profile_fail(pname, "requires_vpn must be true or false")
  }
  out <- list(name = pname, method = method, requires_vpn = vpn)
  region <- profile$oda_region
  if (!is.null(region)) {
    if (!identical(method, "iom")) {
      .sashiny_profile_fail(pname, "oda_region needs method iom")
    }
    if (!is.character(region) || !region %in% names(.sashiny_oda_hosts)) {
      .sashiny_profile_fail(pname, paste(
        "unknown oda_region; expected one of", paste(names(.sashiny_oda_hosts), collapse = ", ")
      ))
    }
    out$kind <- "oda"
    out$oda_region <- region
    out$endpoints <- paste0(.sashiny_oda_hosts[[region]], ":8591")
    out$env <- c(SASHINY_LICENSE_ACK = "true", SASHINY_PROFILE = "oda", SASHINY_ODA_REGION = region)
  } else if (identical(method, "iom")) {
    if (is.null(profile$iomhost)) {
      .sashiny_profile_fail(pname, "an iom profile needs oda_region or iomhost")
    }
    host <- .sashiny_profile_safe(pname, "iomhost", profile$iomhost)
    port <- profile$iomport %||% 8591L
    if (!is.numeric(port) || length(port) != 1L || is.na(port) || port != round(port) ||
      port < 1 || port > 65535) {
      .sashiny_profile_fail(pname, "iomport must be an integer from 1 to 65535")
    }
    port <- format(as.integer(port))
    out$kind <- "sas94"
    out$endpoints <- paste0(host, ":", port)
    out$env <- c(
      SASHINY_LICENSE_ACK = "true", SASHINY_PROFILE = "sas94",
      SASHINY_SAS94_HOST = host, SASHINY_SAS94_PORT = port
    )
  } else if (identical(method, "http")) {
    url <- profile$url
    if (!is.character(url) || length(url) != 1L || !grepl("^https?://", url)) {
      .sashiny_profile_fail(pname, "an http profile needs a url starting with https:// or http://")
    }
    .sashiny_profile_safe(pname, "url", url)
    authority <- sub("^https?://([^/?#]*).*$", "\\1", url)
    authority <- sub("^[^@]*@", "", authority)
    host <- sub(":[0-9]*$", "", authority)
    if (!nzchar(host)) {
      .sashiny_profile_fail(pname, "url has no host")
    }
    port <- if (grepl(":[0-9]+$", authority)) {
      sub("^.*:([0-9]+)$", "\\1", authority)
    } else if (startsWith(url, "https://")) {
      "443"
    } else {
      "80"
    }
    out$kind <- "viya"
    out$endpoints <- paste0(tolower(host), ":", port)
    out$env <- c(SASHINY_LICENSE_ACK = "true", SASHINY_PROFILE = "viya", SASHINY_VIYA_URL = url)
  } else {
    if (is.null(profile$host) || is.null(profile$saspath)) {
      .sashiny_profile_fail(pname, "an ssh profile needs host and saspath")
    }
    host <- .sashiny_profile_safe(pname, "host", profile$host)
    saspath <- .sashiny_profile_safe(pname, "saspath", profile$saspath, path = TRUE)
    out$kind <- "sas94"
    out$endpoints <- paste0(host, ":22")
    out$env <- c(
      SASHINY_LICENSE_ACK = "true", SASHINY_PROFILE = "sas94",
      SASHINY_SAS94_HOST = host, SASHINY_SAS94_SASPATH = saspath
    )
  }
  out$needs_java <- identical(method, "iom")
  out$secrets <- if (identical(method, "ssh")) character(0) else c("SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD")
  structure(out, class = "sashiny_profile")
}

#' @export
print.sashiny_profile <- function(x, ...) {
  cat("<sashiny profile ", x$name, ">\n", sep = "")
  cat("  kind:", x$kind, "| method:", x$method, "| requires_vpn:", x$requires_vpn, "\n")
  cat("  endpoints:", paste(x$endpoints, collapse = ", "), "\n")
  invisible(x)
}

#' Build the engine of a deployed app from its environment
#'
#' Reads `SASHINY_PROFILE` (`"oda"`, `"viya"` or `"sas94"`) and the connection
#' variables a deployment target sets (spec section 6.8), then calls
#' [sas_connect()]. Use it as the engine factory of a deployed app, for example
#' `sas_pool(sas_connect_env, max_size = 2L)`.
#'
#' @param license_ack Passed to [sas_connect()]. `NULL` (the default) defers to
#'   `SASHINY_LICENSE_ACK`, which deployment targets set.
#' @return A `sashiny_engine_saspy` object. No 'SAS' session is started.
#' @examples
#' old <- Sys.getenv(c("SASHINY_PROFILE", "SASHINY_ODA_REGION"), unset = NA)
#' Sys.setenv(SASHINY_PROFILE = "oda", SASHINY_ODA_REGION = "eu1")
#' sas_connect_env()$backend
#' for (n in names(old)) {
#'   if (is.na(old[[n]])) Sys.unsetenv(n) else do.call(Sys.setenv, as.list(old[n]))
#' }
#' @export
sas_connect_env <- function(license_ack = NULL) {
  env <- function(name) {
    value <- Sys.getenv(name, unset = "")
    if (nzchar(value)) value else NULL
  }
  kind <- env("SASHINY_PROFILE") %||% ""
  if (identical(kind, "oda")) {
    return(sas_connect("oda", region = env("SASHINY_ODA_REGION") %||% "us1", license_ack = license_ack))
  }
  if (identical(kind, "viya")) {
    url <- env("SASHINY_VIYA_URL")
    if (is.null(url)) .sashiny_abort("deploy", "SASHINY_VIYA_URL is required when SASHINY_PROFILE=viya")
    return(sas_connect("viya", url = url, license_ack = license_ack))
  }
  if (identical(kind, "sas94")) {
    host <- env("SASHINY_SAS94_HOST")
    if (is.null(host)) .sashiny_abort("deploy", "SASHINY_SAS94_HOST is required when SASHINY_PROFILE=sas94")
    port <- as.integer(env("SASHINY_SAS94_PORT") %||% "8591")
    return(sas_connect("sas94",
      host = host, port = port, saspath = env("SASHINY_SAS94_SASPATH"),
      license_ack = license_ack
    ))
  }
  .sashiny_abort("deploy", "SASHINY_PROFILE must be oda, viya or sas94")
}
