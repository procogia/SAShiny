# saspy engine with selectable connection profiles (issue #6).
#
# Implements the run protocol (spec section 6.1), dataset upload conversion
# (section 7), result collection (section 8) and run status (section 6.5)
# against live SAS 9.4 / Viya via saspy, reached through reticulate. Connection
# profiles are chosen per app or session; credentials come only from
# ~/.authinfo or environment variables, never from the contract.
#
# Live verification is deferred to the live SAS check reports (issue #11); this
# module implements the interface and profile loading.

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
  lines <- strsplit(log, "\n", fixed = TRUE)[[1]]
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
  m <- regexpr(paste0("SASHINY-END run=", run_id, " syscc=([0-9]+)"), log, perl = TRUE)
  if (m == -1L) {
    return(list(status = "error", syscc = NULL))
  }
  syscc <- as.integer(sub(".*syscc=([0-9]+).*", "\\1",
                          regmatches(log, m)))
  counts <- .sashiny_classify_log(log)
  if (syscc > 4L || counts[["error"]] > 0L) {
    return(list(status = "error", syscc = syscc))
  }
  if (syscc == 4L || counts[["warning"]] > 0L) {
    return(list(status = "warning", syscc = syscc))
  }
  list(status = "success", syscc = syscc)
}

#' Create a saspy engine
#'
#' A live SAS engine backed by saspy, reached through reticulate. Requires the
#' `reticulate` and `saspy` packages (optional).
#'
#' @param cfg The saspy configuration (a list or a path to a config file).
#' @param cfgname The saspy config name.
#' @return A `sashiny_engine_saspy` object (a named list).
#' @export
sas_engine_saspy <- function(cfg, cfgname = "sashiny") {
  structure(
    list(cfg = cfg, cfgname = cfgname, sas = NULL),
    class = "sashiny_engine_saspy"
  )
}

#' Run a contract with the saspy engine
#'
#' @param engine A `sashiny_engine_saspy` object.
#' @param contract A `sashiny_contract` object.
#' @param values A named list of input values.
#' @param today A `Date` used to resolve `"today"`.
#' @param uploads A named list mapping dataset input ids to `TRUE`.
#' @param run_id The run identifier.
#' @return A `sashiny_result` object.
#' @export
sas_engine_saspy_run <- function(engine, contract, values, today = Sys.Date(),
                                 uploads = NULL, run_id = NULL) {
  rlang::check_installed("reticulate", reason = "to run live SAS via saspy")
  run_id <- run_id %||% .sashiny_run_id()
  data <- contract$data
  res <- sas_render_values(data, values, today, uploads = uploads)
  macros <- res$macros
  if (length(res$issues) > 0L) {
    return(sashiny_result(run_id, "error",
                          metadata = .sashiny_metadata(run_id, "error",
                                                       macros = macros,
                                                       engine = "saspy",
                                                       engine_version = "0.0.1")))
  }

  sas <- .sashiny_saspy_session(engine)
  if ((data$run %||% list())$reset_work %||% TRUE) {
    sas$submit(sas_reset_code(data), results = "TEXT")
  }
  program <- readBin(file.path(contract$base_dir, data$program), "raw",
                     n = file.info(file.path(contract$base_dir, data$program))$size)
  res <- sas$submit(sas_wrapper_code(data, macros, program, run_id = run_id),
                    results = "HTML")
  status <- .sashiny_run_status(res$LOG, run_id)
  result <- sashiny_result(
    run_id, status$status,
    log = res$LOG,
    metadata = .sashiny_metadata(run_id, status$status, macros = macros,
                                 engine = "saspy", engine_version = "0.0.1")
  )
  result$metadata$syscc <- status$syscc
  result
}

#' Get (or create) the underlying saspy session via reticulate.
#' @noRd
.sashiny_saspy_session <- function(engine) {
  if (!is.null(engine$sas)) {
    return(engine$sas)
  }
  saspy <- reticulate::import("saspy")
  engine$sas <- saspy$SASsession(cfgfile = engine$cfg, cfgname = engine$cfgname,
                                 results = "HTML")
  engine$sas
}