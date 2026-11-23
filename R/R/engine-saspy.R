# saspy engine with selectable connection profiles (issue #6).
#
# Connections are limited to 'SAS' 9.4, 'SAS Viya' and 'SAS OnDemand for
# Academics' (spec section 6.6), reached through saspy and reticulate.
# Credentials come only from ~/.authinfo or environment variables, never from
# the contract or function arguments.
#
# This file holds profile loading, run status and the connection builder; the
# engine itself is in engine-saspy-run.R.

#' Load connection profiles from a YAML file
#'
#' @param path Path to the connections file. Defaults to `SASHINY_CONNECTIONS`
#'   or `~/.config/sashiny/connections.yml`.
#' @return A named list with `default` and `profiles`.
#' @export
sas_load_profiles <- function(path = NULL) {
  if (is.null(path)) {
    path <- Sys.getenv("SASHINY_CONNECTIONS", unset = "")
    if (!nzchar(path)) {
      path <- file.path("~", ".config", "sashiny", "connections.yml")
    }
  }
  path <- normalizePath(path, mustWork = FALSE)
  if (!file.exists(path)) {
    return(list(default = NULL, profiles = list()))
  }
  yaml::read_yaml(path)
}

#' Classify log lines (spec section 6.5)
#'
#' @param log The SAS log text.
#' @return A named integer vector with `error` and `warning` counts.
#' @noRd
.sashiny_classify_log <- function(log) {
  lines <- .sashiny_split_log(log)
  c(
    error = sum(startsWith(lines, "ERROR")),
    warning = sum(startsWith(lines, "WARNING"))
  )
}

#' Determine run status from the log (spec section 6.5)
#'
#' @param log The SAS log text.
#' @param run_id The run identifier.
#' @return A list with `status` and `syscc`.
#' @noRd
.sashiny_run_status <- function(log, run_id = "fixture") {
  # Anchor to an executed NOTE sentinel line, not a numbered source echo
  # (spec section 6.5): the line must start with "NOTE: SASHINY-END run=<id> syscc=<n>".
  lines <- .sashiny_split_log(log)
  end <- grep(paste0("^NOTE: SASHINY-END run=", run_id, " syscc=([0-9]+)$"), lines)
  if (length(end) == 0L) {
    return(list(status = "error", syscc = NULL))
  }
  syscc <- as.integer(sub(
    paste0("^NOTE: SASHINY-END run=", run_id, " syscc=([0-9]+)$"), "\\1",
    lines[end[[1]]]
  ))
  counts <- .sashiny_classify_log(log)
  if (syscc > 4L || counts[["error"]] > 0L) {
    return(list(status = "error", syscc = syscc))
  }
  if (syscc == 4L || counts[["warning"]] > 0L) {
    return(list(status = "warning", syscc = syscc))
  }
  list(status = "success", syscc = syscc)
}

# ODA hosts by region (spec/tools/live_sas_check.py).
.sashiny_oda_hosts <- list(
  us1 = c("odaws01-usw2.oda.sas.com", "odaws02-usw2.oda.sas.com"),
  us2 = c("odaws01-usw2-2.oda.sas.com", "odaws02-usw2-2.oda.sas.com"),
  eu1 = c("odaws01-euw1.oda.sas.com", "odaws02-euw1.oda.sas.com"),
  ap1 = c("odaws01-apse1.oda.sas.com", "odaws02-apse1.oda.sas.com"),
  ap2 = c("odaws01-apse1-2.oda.sas.com", "odaws02-apse1-2.oda.sas.com")
)

#' Build a SAS engine for one of the three supported 'SAS' systems
#'
#' SAShiny runs programs only on a live 'SAS' system: 'SAS' 9.4 (IOM or SSH),
#' 'SAS Viya' (HTTP) or 'SAS OnDemand for Academics' (ODA). There is no
#' offline mode. You choose the backend explicitly and supply its connection
#' details; SAShiny does not auto-detect the 'SAS' version.
#'
#' @section Licence responsibility:
#' 'SAS' is commercial software. **You are responsible for holding a valid
#' licence** (or, for ODA, for accepting its terms of use) for the system you
#' connect to. SAShiny cannot verify a licence, so it asks you to acknowledge
#' this explicitly: a run fails with "SAS licence not acknowledged" unless
#' `license_ack = TRUE`, `options(SAShiny.license_ack = TRUE)` or the
#' environment variable `SASHINY_LICENSE_ACK=true` is set.
#'
#' @section Credentials:
#' Credentials are never passed as arguments. They come from `~/.authinfo`
#' (`_authinfo` in `USERPROFILE` on Windows), keyed by the profile's
#' `authkey` (`oda`, `viya` or `iom`), or, on hosted platforms such as Posit
#' Connect, from the environment variables `SASHINY_SAS_USER` and
#' `SASHINY_SAS_PASSWORD` (see [sas_publish()]). SSH uses key-based login.
#'
#' @param backend A backend from [sas_oda()], [sas_viya()], [sas_94_iom()] or
#'   [sas_94_ssh()]. The old form, a profile name `"oda"`, `"viya"` or
#'   `"sas94"` with the connection arguments in `...`, still works with a
#'   deprecation warning.
#' @param license_ack `TRUE` to acknowledge that you are licensed to use the
#'   'SAS' system you connect to (see the "Licence responsibility" section).
#'   `NULL` (the default) defers to the `SAShiny.license_ack` option and the
#'   `SASHINY_LICENSE_ACK` environment variable.
#' @param ... Old form only: `region`, `url`, `context`, `verify`, `host`,
#'   `port`, `saspath`, `ssh_user` and `java`.
#' @return A `sashiny_engine_saspy` object configured for the chosen backend.
#'   No 'SAS' session is started until the first run.
#' @examples
#' # Builds the configuration only: no 'SAS' session is started and nothing
#' # is sent over the network.
#' engine <- sas_connect(sas_oda("us1"))
#' engine$backend
#' engine$cfg$authkey
#' \dontrun{
#' # Needs an ODA account, Java, Python with saspy and credentials in
#' # ~/.authinfo; not run during checks.
#' engine <- sas_connect(sas_oda("us1"), license_ack = TRUE)
#' sas_close(engine)
#' }
#' @export
sas_connect <- function(backend, license_ack = NULL, ...) {
  if (is.character(backend)) {
    lifecycle::deprecate_soft("0.3.1", "sas_connect(profile = )",
      details = paste0(
        "Pass a backend: `sas_connect(sas_oda())`, `sas_viya()`, ",
        "`sas_94_iom()` or `sas_94_ssh()`."
      )
    )
    backend <- .sashiny_legacy_backend(backend, ...)
  } else if (...length() > 0L) {
    .sashiny_abort("engine", "connection arguments go to the backend constructor, not sas_connect()")
  }
  if (!inherits(backend, "sashiny_backend")) {
    .sashiny_abort("engine",
      "backend must come from sas_oda(), sas_viya(), sas_94_iom() or sas_94_ssh()")
  }
  sas_engine_saspy(backend$cfg, license_ack = license_ack)
}

#' 'SAS' backends for [sas_connect()]
#'
#' One constructor per supported 'SAS' system (spec section 6.6). Each
#' validates only its own arguments and returns a `sashiny_backend` object for
#' [sas_connect()]. Nothing is sent over the network.
#'
#' - `sas_oda()`: 'SAS OnDemand for Academics' (IOM, needs Java).
#' - `sas_viya()`: 'SAS Viya' over HTTP(S).
#' - `sas_94_iom()`: 'SAS' 9.4 over IOM (needs Java).
#' - `sas_94_ssh()`: 'SAS' 9.4 over SSH (key-based login).
#'
#' @param region ODA region: `"us1"`, `"us2"`, `"eu1"`, `"ap1"` or `"ap2"`.
#' @param java Path to the Java executable (optional; auto-detected).
#' @param url 'SAS Viya' base URL, starting with `https://` or `http://`.
#' @param context 'SAS Viya' compute context name (optional).
#' @param verify Verify 'SAS Viya' TLS certificates (default `TRUE`).
#' @param host 'SAS' 9.4 host name.
#' @param port 'SAS' 9.4 IOM port (default `8591`).
#' @param saspath 'SAS' 9.4 executable path on the SSH host.
#' @param ssh_user SSH login user (optional).
#' @return A `sashiny_backend` object.
#' @examples
#' sas_oda("eu1")
#' sas_viya("https://viya.example.com")
#' sas_94_iom("sas.example.com")
#' sas_94_ssh("sas.example.com", "/opt/sas/SASHome/SASFoundation/9.4/sas")
#' @name sas_backends
NULL

#' @rdname sas_backends
#' @export
sas_oda <- function(region = c("us1", "us2", "eu1", "ap1", "ap2"), java = NULL) {
  regions <- eval(formals(sas_oda)$region)
  if (identical(region, regions)) region <- regions[[1L]]
  # A sashiny_error_engine, as Python's EngineValueError (not an rlang error).
  if (!is.character(region) || length(region) != 1L || !region %in% regions) {
    .sashiny_abort("engine", sprintf(
      "unknown ODA region %s; expected one of %s",
      paste(format(region), collapse = ", "), paste(regions, collapse = ", ")
    ))
  }
  .sashiny_new_backend("oda", list(
    java = java %||% .sashiny_find_java(),
    iomhost = .sashiny_oda_hosts[[region]],
    iomport = 8591L,
    authkey = "oda",
    encoding = "utf-8"
  ), region = region)
}

#' @rdname sas_backends
#' @export
sas_viya <- function(url, context = NULL, verify = TRUE) {
  if (!is.character(url) || length(url) != 1L || !grepl("^https?://", url)) {
    .sashiny_abort("engine", "url must be one 'SAS Viya' URL starting with https:// or http://")
  }
  if (!is.null(context) && (!is.character(context) || length(context) != 1L)) {
    .sashiny_abort("engine", "context must be one compute context name")
  }
  if (!isTRUE(verify) && !isFALSE(verify)) .sashiny_abort("engine", "verify must be TRUE or FALSE")
  cfg <- list(url = url, authkey = "viya", options = list("fullstimer"))
  if (!is.null(context)) cfg$context <- context
  if (!isTRUE(verify)) cfg$verify <- FALSE
  .sashiny_new_backend("viya", cfg, url = url)
}

#' @rdname sas_backends
#' @export
sas_94_iom <- function(host, port = 8591L, java = NULL) {
  .sashiny_check_host(host)
  if (!is.numeric(port) || length(port) != 1L || port != round(port) || port < 1 || port > 65535) {
    .sashiny_abort("engine", "port must be an integer from 1 to 65535")
  }
  .sashiny_new_backend("sas94_iom", list(
    java = java %||% .sashiny_find_java(),
    iomhost = host,
    iomport = as.integer(port),
    authkey = "iom",
    encoding = "utf-8"
  ), host = host)
}

#' @rdname sas_backends
#' @export
sas_94_ssh <- function(host, saspath, ssh_user = NULL) {
  .sashiny_check_host(host)
  if (!is.character(saspath) || length(saspath) != 1L || !nzchar(saspath)) {
    .sashiny_abort("engine", "saspath must be the path of the 'SAS' executable on the host")
  }
  cfg <- list(
    saspath = saspath,
    ssh = .sashiny_find_ssh(),
    host = host,
    encoding = "utf-8",
    options = list("-fullstimer")
  )
  if (!is.null(ssh_user)) cfg$luser <- ssh_user
  .sashiny_new_backend("sas94_ssh", cfg, host = host)
}

#' @export
print.sashiny_backend <- function(x, ...) {
  detail <- x$region %||% x$url %||% x$host %||% ""
  cat("<sashiny backend> ", x$kind, if (nzchar(detail)) paste0(" (", detail, ")"), "\n", sep = "")
  invisible(x)
}

#' Build a backend object.
#' @noRd
.sashiny_new_backend <- function(kind, cfg, ...) {
  structure(c(list(kind = kind, cfg = cfg), list(...)), class = "sashiny_backend")
}

#' Validate a 'SAS' 9.4 host argument.
#' @noRd
.sashiny_check_host <- function(host) {
  if (!is.character(host) || length(host) != 1L || !nzchar(host)) {
    .sashiny_abort("engine", "host must be one 'SAS' 9.4 host name")
  }
}

#' Translate the deprecated `sas_connect("oda", region = ...)` form.
#' @noRd
.sashiny_legacy_backend <- function(profile, region = "us1", url = NULL, context = NULL,
                                    verify = TRUE, host = NULL, port = 8591L,
                                    saspath = NULL, ssh_user = NULL, java = NULL) {
  if (identical(profile, "oda")) {
    if (!(region %in% names(.sashiny_oda_hosts))) {
      .sashiny_abort("engine",
        "unknown ODA region '", region, "'; expected one of ",
        paste(names(.sashiny_oda_hosts), collapse = ", ")
      )
    }
    return(sas_oda(region, java = java))
  }
  if (identical(profile, "viya")) {
    if (is.null(url)) .sashiny_abort("engine", "url is required for profile 'viya'")
    return(sas_viya(url, context = context, verify = verify))
  }
  if (identical(profile, "sas94")) {
    if (is.null(host)) .sashiny_abort("engine", "host is required for profile 'sas94'")
    if (!is.null(saspath)) return(sas_94_ssh(host, saspath, ssh_user = ssh_user))
    return(sas_94_iom(host, port = port, java = java))
  }
  .sashiny_abort("engine", "unknown profile '", profile, "'; expected 'oda', 'viya' or 'sas94'")
}

#' Locate the Java executable, or NULL when not found.
#'
#' CRAN: only looks the path up (`JAVA_HOME`, `Sys.which()`); nothing is run.
#' @noRd
.sashiny_find_java <- function() {
  java_home <- Sys.getenv("JAVA_HOME", unset = "")
  if (nzchar(java_home)) {
    cand <- file.path(java_home, "bin", if (.Platform$OS.type == "windows") "java.exe" else "java")
    if (file.exists(cand)) {
      return(cand)
    }
  }
  Sys.which("java")
}

#' Locate the SSH executable.
#'
#' CRAN: only looks the path up with `Sys.which()`; nothing is run.
#' @noRd
.sashiny_find_ssh <- function() {
  ssh <- Sys.which("ssh")
  if (nzchar(ssh)) ssh else "/usr/bin/ssh"
}
