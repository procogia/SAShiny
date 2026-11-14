# saspy engine with selectable connection profiles (issue #6).
#
# Implements the run protocol (spec section 6.1), dataset upload conversion
# (section 7), result collection (section 8) and run status (section 6.5)
# against live SAS 9.4 / Viya via saspy, reached through reticulate. Connection
# profiles are chosen per app or session; credentials come only from
# ~/.authinfo or environment variables, never from the contract.
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
    return(list(default = "offline", profiles = list()))
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
  # (spec §6.5): the line must start with "NOTE: SASHINY-END run=<id> syscc=<n>".
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

#' Build a SAS engine for one of three connection types
#'
#' The consumer chooses the backend explicitly and supplies its connection
#' details. SAShiny does not auto-detect or validate the SAS version: the
#' responsibility for pointing at the correct endpoint/version rests with the
#' caller. Credentials are never passed here — they come from `~/.authinfo`
#' keyed by the profile's `authkey`.
#'
#' @param profile One of `"oda"`, `"viya"` or `"sas94"`. Required; there is no
#'   default.
#' @param region ODA region (`us1`/`us2`/`eu1`/`ap1`/`ap2`). Defaults to `us1`.
#' @param url Viya base URL (required for `viya`).
#' @param context Viya compute context name (optional).
#' @param verify Viya TLS verification (default `TRUE`).
#' @param host SAS 9.4 host (required for `sas94`).
#' @param port SAS 9.4 IOM port (default `8591`).
#' @param saspath SAS 9.4 executable path for SSH (optional; when given, SSH is
#'   used instead of IOM).
#' @param ssh_user SSH login user (optional).
#' @param java Path to the Java executable for IOM (optional; auto-detected when
#'   omitted).
#' @param record_to Directory where every run is also saved as a recording
#'   (spec section 8.3) for offline replay with [sas_engine_mock()].
#' @return A `sashiny_engine_saspy` object configured for the chosen backend.
#' @examples
#' # Build the config for an ODA connection (no live SAS session is started).
#' engine <- sas_connect("oda", region = "us1")
#' engine$cfg$authkey
#' @export
sas_connect <- function(profile, region = "us1", url = NULL, context = NULL,
                        verify = TRUE, host = NULL, port = 8591L,
                        saspath = NULL, ssh_user = NULL, java = NULL,
                        record_to = NULL) {
  if (identical(profile, "oda")) {
    if (!(region %in% names(.sashiny_oda_hosts))) {
      stop(
        "unknown ODA region '", region, "'; expected one of ",
        paste(names(.sashiny_oda_hosts), collapse = ", ")
      )
    }
    cfg <- list(
      java = java %||% .sashiny_find_java(),
      iomhost = .sashiny_oda_hosts[[region]],
      iomport = 8591L,
      authkey = "oda",
      encoding = "utf-8"
    )
  } else if (identical(profile, "viya")) {
    if (is.null(url)) {
      stop("url is required for profile 'viya'")
    }
    cfg <- list(url = url, authkey = "viya", options = list("fullstimer"))
    if (!is.null(context)) {
      cfg$context <- context
    }
    if (!isTRUE(verify)) {
      cfg$verify <- FALSE
    }
  } else if (identical(profile, "sas94")) {
    if (is.null(host)) {
      stop("host is required for profile 'sas94'")
    }
    if (!is.null(saspath)) {
      cfg <- list(
        saspath = saspath,
        ssh = .sashiny_find_ssh(),
        host = host,
        encoding = "utf-8",
        options = list("-fullstimer")
      )
      if (!is.null(ssh_user)) {
        cfg$luser <- ssh_user
      }
    } else {
      cfg <- list(
        java = java %||% .sashiny_find_java(),
        iomhost = host,
        iomport = port,
        authkey = "iom",
        encoding = "utf-8"
      )
    }
  } else {
    stop("unknown profile '", profile, "'; expected 'oda', 'viya' or 'sas94'")
  }

  sas_engine_saspy(cfg, record_to = record_to)
}

#' Locate the Java executable, or NULL when not found.
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
#' @noRd
.sashiny_find_ssh <- function() {
  ssh <- Sys.which("ssh")
  if (nzchar(ssh)) ssh else "/usr/bin/ssh"
}
