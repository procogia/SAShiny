# The live saspy engine: session, run protocol and result collection.
#
# Implements the run protocol (spec section 6.1), the reset (6.2), the
# `choices_from` query (6.4), dataset uploads (7) and result collection (8)
# against SAS 9.4 or SAS Viya through saspy and reticulate. The session is any
# object with saspy's `submit`, `sd2df`, `df2sd`, `download` and `endsas`
# methods: a real saspy session, or a fake in tests.

#' Create a saspy engine
#'
#' A live SAS engine backed by saspy, reached through reticulate. The SAS
#' session starts on the first run and is reused for later runs (each run
#' resets WORK, spec section 6.2); it is restarted automatically after a
#' failure. Use [sas_pool()] to serve several users. Most apps build the engine
#' with [sas_connect()].
#'
#' Only 'SAS' 9.4 (IOM or SSH), 'SAS Viya' (HTTP) and 'SAS OnDemand for
#' Academics' (IOM) configurations are accepted (spec section 6.6). Running a
#' program also requires the licence acknowledgement described in
#' [sas_connect()].
#'
#' @param cfg A saspy configuration (a named list, written to a temporary
#'   `sascfg` file) or the path of an existing saspy configuration file. A
#'   configuration file cannot be inspected; you are responsible for it
#'   pointing at a supported, licensed 'SAS' system.
#' @param cfgname The configuration name inside that file.
#' @param license_ack `TRUE` to acknowledge that you hold a valid licence for
#'   the 'SAS' system this engine connects to. `NULL` (the default) defers to
#'   the `SAShiny.license_ack` option and the `SASHINY_LICENSE_ACK`
#'   environment variable.
#' @return A `sashiny_engine_saspy` object (an environment). No 'SAS' session
#'   is started until the first run.
#' @examples
#' # Builds the configuration only; no 'SAS' session is started.
#' engine <- sas_engine_saspy(list(java = "java", iomhost = "sas.example.com", iomport = 8591))
#' engine$backend
#' @export
sas_engine_saspy <- function(cfg, cfgname = "sashiny", license_ack = NULL) {
  backend <- .sashiny_backend(cfg)
  .sashiny_new_saspy_engine(cfg, cfgname, license_ack = license_ack, backend = backend)
}

#' Build a saspy engine without validating its configuration.
#'
#' Internal constructor behind [sas_engine_saspy()]. `session_factory` is a
#' testing hook (a function returning a fake saspy session) used by the test
#' suite, which runs without 'SAS'. It is deliberately not exported: a public
#' factory would let a caller supply 'SAS' logs that never came from 'SAS'
#' (spec section 6.6).
#' @noRd
.sashiny_new_saspy_engine <- function(cfg, cfgname = "sashiny", session_factory = NULL,
                                      license_ack = NULL, backend = NULL) {
  engine <- new.env(parent = emptyenv())
  engine$cfg <- cfg
  engine$cfgname <- cfgname
  engine$backend <- backend %||% if (is.null(session_factory)) .sashiny_backend(cfg) else "test"
  engine$license_ack <- license_ack
  engine$session_factory <- session_factory
  engine$sas <- NULL
  engine$sas_version <- NULL
  engine$choices <- list()
  engine$tmpdir <- NULL
  class(engine) <- c("sashiny_engine_saspy", "sashiny_engine")
  engine
}

#' @export
print.sashiny_engine_saspy <- function(x, ...) {
  cat("<sashiny saspy engine>\n")
  cat("  backend:", x$backend %||% "", "\n")
  cat("  session:", if (is.null(x$sas)) "not started" else "started", "\n")
  cat("  licence acknowledged:", if (.sashiny_license_ok(x)) "yes" else "no", "\n")
  invisible(x)
}

#' Identify the supported backend of a saspy configuration (spec section 6.6).
#'
#' Returns `"oda"`, `"viya"`, `"sas94-iom"`, `"sas94-ssh"` or `"cfgfile"`, and
#' stops for anything else (local Windows COM, local STDIO, unknown methods).
#' @noRd
.sashiny_backend <- function(cfg) {
  supported <- "supported backends are 'SAS' 9.4 (IOM or SSH), 'SAS Viya' and 'SAS OnDemand for Academics'"
  if (is.character(cfg) && length(cfg) == 1L && nzchar(cfg)) {
    return("cfgfile")
  }
  if (!is.list(cfg) || length(cfg) == 0L || is.null(names(cfg))) {
    .sashiny_abort("engine", "cfg must be a named list or the path of a saspy configuration file; ", supported)
  }
  if (!is.null(cfg$provider) || !is.null(cfg$colocal)) {
    .sashiny_abort("engine", "local 'SAS' (COM) connections are not supported; ", supported)
  }
  methods <- c(
    http = !is.null(cfg$url),
    iom = !is.null(cfg$iomhost),
    ssh = !is.null(cfg$saspath) && !is.null(cfg$host)
  )
  if (sum(methods) != 1L) {
    if (!is.null(cfg$saspath) && is.null(cfg$host)) {
      .sashiny_abort("engine", "local 'SAS' (STDIO) connections are not supported; ", supported)
    }
    .sashiny_abort("engine", "cfg must describe exactly one connection (url, iomhost, or saspath + host); ",
      supported)
  }
  if (methods[["http"]]) {
    if (!grepl("^https?://", cfg$url)) {
      .sashiny_abort("engine", "the 'SAS Viya' url must start with https:// or http://")
    }
    return("viya")
  }
  if (methods[["iom"]]) {
    hosts <- unlist(cfg$iomhost)
    if (length(hosts) > 0L && all(grepl("\\.oda\\.sas\\.com$", hosts))) {
      return("oda")
    }
    if (length(hosts) != 1L) {
      .sashiny_abort("engine", "a 'SAS' 9.4 IOM configuration needs exactly one iomhost")
    }
    return("sas94-iom")
  }
  "sas94-ssh"
}

#' Whether the user has acknowledged licence responsibility (spec section 6.6).
#'
#' An explicit `license_ack` on the engine wins; otherwise the
#' `SAShiny.license_ack` option, then the `SASHINY_LICENSE_ACK` environment
#' variable (`true` or `1`, used by deployed apps).
#' @noRd
.sashiny_license_ok <- function(engine = NULL) {
  explicit <- if (is.null(engine)) NULL else engine$license_ack
  if (!is.null(explicit)) {
    return(isTRUE(explicit))
  }
  if (isTRUE(getOption("SAShiny.license_ack"))) {
    return(TRUE)
  }
  tolower(Sys.getenv("SASHINY_LICENSE_ACK", unset = "")) %in% c("true", "1")
}

#' The error raised or reported when the licence is not acknowledged.
#' @noRd
.sashiny_license_message <- paste(
  "SAS licence not acknowledged: SAShiny runs programs only on a 'SAS' system you are licensed",
  "to use. Confirm this with license_ack = TRUE, options(SAShiny.license_ack = TRUE) or the",
  "environment variable SASHINY_LICENSE_ACK=true."
)

#' Saspy session keyword arguments from `SASHINY_SAS_USER`/`SASHINY_SAS_PASSWORD`.
#'
#' Used on hosted platforms such as Posit Connect, where credentials live in
#' the content's environment variables (spec section 6.7). The values go only
#' to saspy; they are never written to a file or a log. Returns an empty list
#' when either variable is unset or for SSH (key-based login).
#' @noRd
.sashiny_env_credentials <- function(cfg) {
  user <- Sys.getenv("SASHINY_SAS_USER", unset = "")
  password <- Sys.getenv("SASHINY_SAS_PASSWORD", unset = "")
  if (!nzchar(user) || !nzchar(password) || !is.list(cfg)) {
    return(list())
  }
  if (!is.null(cfg$iomhost)) {
    return(list(omruser = user, omrpw = password))
  }
  if (!is.null(cfg$url)) {
    return(list(user = user, pw = password))
  }
  list()
}

#' Write a saspy configuration file defining `cfgname` from a list.
#' @noRd
.sashiny_write_cfgfile <- function(cfg, cfgname, folder) {
  if (!grepl("^[A-Za-z_][A-Za-z0-9_]*$", cfgname)) {
    .sashiny_abort("engine", "cfgname must be a Python identifier: ", cfgname)
  }
  json <- as.character(jsonlite::toJSON(cfg, auto_unbox = TRUE, null = "null", digits = NA))
  quotes <- strrep("'", 3L)
  if (grepl(quotes, json, fixed = TRUE)) {
    .sashiny_abort("engine", "the saspy configuration cannot contain three single quotes")
  }
  path <- file.path(folder, paste0("sascfg_", cfgname, ".py"))
  writeLines(c(
    "# Generated by SAShiny; do not edit.",
    "import json",
    sprintf("SAS_config_names = ['%s']", cfgname),
    sprintf("%s = json.loads(r%s%s%s)", cfgname, quotes, json, quotes)
  ), path, useBytes = TRUE)
  path
}

#' Get (or start) the engine's SAS session.
#' @noRd
.sashiny_saspy_session <- function(engine) {
  if (!is.null(engine$sas)) {
    return(engine$sas)
  }
  sas <- .sashiny_saspy_open(engine)
  # Session setup (spec 6.1): ODA starts with NONOTES, which hides the sentinels.
  # Retain the session before setup so a setup failure can still close it; a
  # session lost here would otherwise leak (spec section 6.5).
  engine$sas <- sas
  tryCatch(
    sas$submit(.sashiny_session_setup_code, results = "TEXT"),
    error = function(e) {
      .sashiny_discard_session(engine)
      stop(e)
    }
  )
  engine$sas
}

#' Submitted once per new SAS session (spec section 6.1).
#' @noRd
.sashiny_session_setup_code <- "/* SAShiny 1 session */\noptions notes;\n"

#' Open a new SAS session (saspy, or the testing factory).
#' @noRd
.sashiny_saspy_open <- function(engine) {
  if (!.sashiny_license_ok(engine)) {
    .sashiny_abort("license", .sashiny_license_message)
  }
  if (!is.null(engine$session_factory)) {
    return(engine$session_factory())
  }
  credentials <- .sashiny_env_credentials(engine$cfg)
  if (is.list(engine$cfg)) .sashiny_preflight(engine$cfg, check_authinfo = length(credentials) == 0L)
  # reticulate 1.45.0 is the first release that converts pandas 3 data frames.
  .sashiny_need("reticulate", "to run live SAS via saspy", version = "1.45.0")
  saspy <- reticulate::import("saspy")
  cfgfile <- engine$cfg
  if (is.list(cfgfile)) {
    # CRAN: the generated saspy configuration (no credentials) is written under
    # tempdir() and removed by sas_close().
    if (is.null(engine$tmpdir)) {
      engine$tmpdir <- tempfile("sashiny-cfg-")
      dir.create(engine$tmpdir)
    }
    cfgfile <- .sashiny_write_cfgfile(engine$cfg, engine$cfgname, engine$tmpdir)
  }
  do.call(saspy$SASsession, c(
    list(cfgfile = cfgfile, cfgname = engine$cfgname, results = "HTML"),
    credentials
  ))
}

#' The saspy credentials file: `~/.authinfo`, or `_authinfo` in `USERPROFILE`
#' on Windows.
#' @noRd
.sashiny_authinfo_path <- function() {
  if (.Platform$OS.type == "windows") {
    home <- Sys.getenv("USERPROFILE", unset = path.expand("~"))
    return(file.path(home, "_authinfo"))
  }
  file.path(path.expand("~"), ".authinfo")
}

#' Fail fast on settings saspy would reject or prompt for.
#'
#' saspy prompts on stdin for a user id and password when the `authkey` is
#' missing from the authinfo file, which would hang a Shiny app, and it reports
#' a missing Java as an invalid configuration.
#' @noRd
.sashiny_preflight <- function(cfg, authinfo = .sashiny_authinfo_path(), check_authinfo = TRUE) {
  java <- cfg$java
  if (!is.null(cfg$iomhost) && (is.null(java) || !nzchar(java))) {
    .sashiny_abort("engine",
      "Java was not found; IOM connections (ODA, SAS 9.4) need Java 8 or later. ",
      "Install it, set JAVA_HOME, or pass java = \"/path/to/java\".")
  }
  key <- cfg$authkey
  if (check_authinfo && !is.null(key)) {
    lines <- if (file.exists(authinfo)) readLines(authinfo, warn = FALSE) else character(0)
    first <- vapply(strsplit(trimws(lines), "[[:space:]]+"), function(w) w[1] %||% "", "")
    if (!key %in% first) {
      .sashiny_abort("engine", sprintf(
        "no credentials for '%s' in %s. Add a line: %s user <user id> password <password>",
        key, authinfo, key
      ))
    }
  }
  invisible(TRUE)
}

#' Submit code and return `list(LOG, LST)`.
#' @noRd
.sashiny_submit <- function(engine, code, results = "TEXT") {
  res <- .sashiny_saspy_session(engine)$submit(code, results = results)
  list(LOG = res$LOG %||% "", LST = res$LST %||% "")
}

#' The SAS version (`&SYSVLONG`), read once per session.
#' @noRd
.sashiny_saspy_version <- function(engine) {
  if (is.null(engine$sas_version)) {
    engine$sas_version <- tryCatch(
      {
        log <- .sashiny_submit(engine, "%put SXVER=&sysvlong;")$LOG
        # Only a line starting with SXVER=; the source echo also contains it.
        hit <- grep("^SXVER=", .sashiny_split_log(log), value = TRUE)
        if (length(hit)) sub("^SXVER=([^[:space:]]+).*$", "\\1", hit[[1]]) else ""
      },
      error = function(e) ""
    )
  }
  engine$sas_version
}

#' @export
sas_engine_close.sashiny_engine_saspy <- function(engine) {
  .sashiny_worker_close(engine)
  engine$choices <- list()
  engine$sas_version <- NULL
  if (!is.null(engine$sas)) {
    sas <- engine$sas
    engine$sas <- NULL
    try(sas$endsas(), silent = TRUE)
  }
  if (!is.null(engine$tmpdir)) {
    unlink(engine$tmpdir, recursive = TRUE)
    engine$tmpdir <- NULL
  }
  invisible(NULL)
}

#' Close the current session (if any) and forget it.
#'
#' Used when a run fails or times out: the session must be ended before the
#' reference is lost, otherwise it leaks (spec section 6.5).
#' @noRd
.sashiny_discard_session <- function(engine) {
  .sashiny_clear_choices(engine)
  sas <- engine$sas
  engine$sas <- NULL
  # Session-scoped caches are invalid once the session is gone (spec section 6.4 reads
  # choices once per session); a replacement session must re-query them.
  engine$choices <- list()
  engine$sas_version <- NULL
  if (!is.null(sas)) {
    try(sas$endsas(), silent = TRUE)
  }
  invisible(NULL)
}

#' @export
sas_engine_choices.sashiny_engine_saspy <- function(engine, contract) {
  if (!isTRUE(engine$in_worker) && (is.null(engine$session_factory) || isTRUE(engine$use_worker))) {
    return(.sashiny_worker_choices(engine, contract))
  }
  inputs <- contract$data$inputs %||% list()
  tag <- .sashiny_contract_sha256(contract)
  if (!nzchar(tag)) tag <- contract$base_dir
  out <- list()
  for (iid in names(inputs)) {
    source <- inputs[[iid]]$choices_from
    if (is.null(source)) next
    key <- paste(tag, iid)
    if (is.null(engine$choices[[key]])) {
      engine$choices[[key]] <- .sashiny_read_choices(engine, source)
    }
    out[[iid]] <- engine$choices[[key]]
  }
  out
}

#' Run the choices query (spec section 6.4) and read the result.
#' @noRd
.sashiny_read_choices <- function(engine, source) {
  on.exit(try(.sashiny_submit(
    engine,
    "proc datasets library=work nolist nowarn; delete _sx_choices; quit;"
  ), silent = TRUE), add = TRUE)
  .sashiny_submit(engine, .sashiny_choices_code(source))
  df <- .sashiny_saspy_session(engine)$sd2df(table = "_sx_choices", libref = "work")
  if (is.null(df)) {
    .sashiny_abort("engine", "could not read choices from ", source$dataset)
  }
  values <- .sashiny_choice_text(.sashiny_df_column(df, source$value_column))
  labels <- if (is.null(source$label_column)) {
    values
  } else {
    .sashiny_choice_text(.sashiny_df_column(df, source$label_column))
  }
  lapply(seq_along(values), function(i) {
    list(value = values[[i]], label = if (nzchar(labels[[i]])) labels[[i]] else values[[i]])
  })
}

#' Choice cells as text (integers without a trailing ".0").
#' @noRd
.sashiny_choice_text <- function(x) {
  if (length(x) == 0L) {
    return(character(0))
  }
  x <- unlist(lapply(x, function(v) if (is.null(v)) NA else v))
  if (is.numeric(x)) {
    return(vapply(x, .sashiny_format_number, character(1)))
  }
  trimws(as.character(x))
}

#' Row count of a `sd2df` result (data frame or reticulate-converted list).
#' @noRd
.sashiny_nrow <- function(df) {
  if (is.null(df)) {
    return(0L)
  }
  n <- nrow(df)
  if (!is.null(n) && length(n) == 1L && !is.na(n)) {
    return(as.integer(n))
  }
  if (is.list(df) && length(df) > 0L) {
    return(as.integer(length(df[[1]])))
  }
  0L
}

#' A data frame column by case-insensitive name.
#' @noRd
.sashiny_df_column <- function(df, name) {
  idx <- match(toupper(name), toupper(names(df)))
  if (is.na(idx)) {
    .sashiny_abort("engine", "column ", name, " not returned by SAS")
  }
  df[[idx]]
}

#' @export
sas_engine_run.sashiny_engine_saspy <- function(engine, contract, values, today = Sys.Date(),
                                                uploads = NULL, run_id = NULL) {
  run_id <- run_id %||% .sashiny_run_id()
  if (!.sashiny_license_ok(engine)) {
    return(.sashiny_engine_error(run_id, list(engine = "saspy"),
      simpleError(.sashiny_license_message)))
  }
  # Spec section 6.5 (session lifetime): the SAS session lives in a persistent
  # worker process that is reused across runs and killed on timeout.
  if (.sashiny_uses_worker(engine, contract)) {
    return(.sashiny_worker_run(engine, contract, values, today, uploads, run_id))
  }
  .sashiny_run_saspy(engine, contract, values, today, uploads, run_id, .sashiny_now(), Sys.time())
}

#' The synchronous saspy run body (spec section 6.1).
#' @noRd
.sashiny_run_saspy <- function(engine, contract, values, today, uploads, run_id, started, t0) {
  data <- contract$data
  flags <- lapply(uploads %||% list(), function(v) !is.null(v) && !isFALSE(v))
  # Fresh choices from the app cache (spec section 6.4) skip the query.
  choices <- contract$cached_choices %||%
    tryCatch(sas_engine_choices(engine, contract), error = function(e) e)
  if (inherits(choices, "error")) {
      .sashiny_discard_session(engine)
    return(.sashiny_engine_error(run_id, list(engine = "saspy"), choices))
  }
  res <- sas_render_values(data, values, today,
    choices_override = .sashiny_choice_override(choices), uploads = flags
  )
  base <- list(
    contract_sha256 = .sashiny_contract_sha256(contract),
    program_sha256 = .sashiny_program_sha256(contract),
    macros = res$macros,
    engine = "saspy",
    engine_version = as.character(utils::packageVersion("SAShiny")),
    started_at = started
  )
  if (length(res$issues) > 0L) {
    return(.sashiny_invalid_result(run_id, base, .sashiny_issue_list(res$issues)))
  }

  submitted <- tryCatch(
    {
      files <- .sashiny_prepare(engine, contract, uploads)
      program <- .sashiny_read_bytes(file.path(contract$base_dir, data$program))
      code <- sas_wrapper_code(data, res$macros, program, run_id = run_id)
      list(files = files, main = .sashiny_submit(engine, code, results = "HTML"))
    },
    sashiny_upload_error = function(e) e,
    error = function(e) e
  )
  if (inherits(submitted, "sashiny_upload_error")) {
    return(.sashiny_invalid_result(run_id, base, list(list(
      code = "V014", message = conditionMessage(submitted)
    ))))
  }
  if (inherits(submitted, "error")) {
      .sashiny_discard_session(engine) # the next run starts a fresh session
    return(.sashiny_engine_error(run_id, base, submitted))
  }

  log <- submitted$main$LOG
  status <- .sashiny_run_status(log, run_id)
  base$sas_version <- .sashiny_saspy_version(engine)
  collected <- .sashiny_collect(engine, data, submitted$main)
  base$ended_at <- .sashiny_now()
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = status$status), base))
  meta$collect_errors <- collected$errors
  meta$syscc <- status$syscc
  meta$seconds <- round(as.numeric(difftime(Sys.time(), t0, units = "secs")), 2)
  meta$backend <- engine$backend
  .sashiny_result(run_id, status$status,
    outputs = collected$outputs, log = log, metadata = meta
  )
}

#' A failed result after an engine/session failure.
#' @noRd
.sashiny_engine_error <- function(run_id, base, condition) {
  # A saspy engine reports the package version, as in Python (spec section 8.4).
  if (identical(base$engine, "saspy") && is.null(base$engine_version)) {
    base$engine_version <- as.character(utils::packageVersion("SAShiny"))
  }
  meta <- do.call(.sashiny_metadata, c(list(run_id = run_id, status = "error"), base))
  meta$engine_error <- conditionMessage(condition)
  .sashiny_result(run_id, "error", metadata = meta)
}

#' Reset the session (section 6.2) and upload dataset inputs (section 7).
#' @noRd
.sashiny_prepare <- function(engine, contract, uploads) {
  data <- contract$data
  if ((data$run %||% list())$reset_work %||% TRUE) {
    .sashiny_submit(engine, sas_reset_code(data))
  }
  files <- .sashiny_resolve_files(contract, uploads)
  for (iid in names(files)) {
    spec <- data$inputs[[iid]]
    read <- .sashiny_read_upload(files[[iid]], spec)
    parts <- strsplit(spec$target, ".", fixed = TRUE)[[1]]
    .sashiny_df2sd(.sashiny_saspy_session(engine), read$df, parts[[1]], parts[[2]], read$datetimes)
  }
  files
}

#' Send a data frame to SAS with `df2sd`
#'
#' Through reticulate, date columns are sent as pandas datetimes so `df2sd`
#' writes SAS dates; other sessions (tests) receive the R data frame.
#'
#' The pandas work runs inside a small Python function. pandas 3 inspects the
#' calling Python frames when a column is assigned, and saspy calls
#' `warnings.warn()` in `df2sd`. Both raise `ValueError: call stack is not deep
#' enough` when reticulate calls them directly from R, with no Python frame
#' above them.
#' @noRd
.sashiny_df2sd <- function(sas, df, lib, mem, datetimes) {
  if (inherits(sas, "python.builtin.object")) {
    dates <- names(datetimes)
    for (n in dates) df[[n]] <- format(df[[n]], "%Y-%m-%d")
    rownames(df) <- NULL
    send <- reticulate::py_run_string(paste(
      "def _sashiny_df2sd(sas, df, mem, lib, dates, dt):",
      "    import pandas as pd",
      "    df = df.reset_index(drop=True)",
      "    for n in dates:",
      "        df[n] = pd.to_datetime(df[n], format='%Y-%m-%d', errors='coerce')",
      "    return sas.df2sd(df, table=mem, libref=lib, datetimes=dt)",
      sep = "\n"
    ), local = TRUE, convert = FALSE)[["_sashiny_df2sd"]]
    send(
      sas, reticulate::r_to_py(df), mem, lib,
      reticulate::r_to_py(as.list(dates)), reticulate::dict(datetimes)
    )
  } else {
    sas$df2sd(df, table = mem, libref = lib, datetimes = datetimes)
  }
  invisible(NULL)
}

# ---------------------------------------------------------------- collection

#' Collect every output per section 8.2; a failure affects only that output.
#' @noRd
.sashiny_collect <- function(engine, data, main) {
  outputs <- list()
  errors <- list()
  for (oid in names(data$outputs)) {
    spec <- data$outputs[[oid]]
    if (.sashiny_is_paired(spec)) {
      paired <- .sashiny_collect_paired(engine, oid, spec, main)
      errors <- c(errors, paired$errors)
      outputs[oid] <- list(paired$value)
      next
    }
    value <- tryCatch(
      .sashiny_collect_one(engine, oid, spec, main),
      error = function(e) structure(list(error = conditionMessage(e)), class = "sashiny_failed")
    )
    if (inherits(value, "sashiny_failed")) {
      errors[[length(errors) + 1L]] <- paste0(oid, ": ", value$error)
      value <- list(error = value$error)
    }
    outputs[oid] <- list(value)
  }
  list(outputs = outputs, errors = errors)
}

#' Collect both parts of a paired output (section 8.2, paired).
#'
#' Each part fails on its own: a failed part's value is `list(error = ...)`
#' and its message is returned as `<output_id>.<part>: <message>`.
#' @noRd
.sashiny_collect_paired <- function(engine, oid, spec, main) {
  parts <- .sashiny_paired_parts(spec)
  chart <- parts$chart
  collectors <- list(
    sas = function() .sashiny_extract_plots(main$LST, parts$select),
    sashiny = function() {
      .sashiny_fetch_table(engine, chart$from, chart$columns,
        as.integer(chart$max_rows %||% 10000L),
        formatted = FALSE
      )
    }
  )
  value <- list()
  errors <- list()
  for (part in names(collectors)) {
    got <- tryCatch(collectors[[part]](), error = function(e) {
      structure(list(error = conditionMessage(e)), class = "sashiny_failed")
    })
    if (inherits(got, "sashiny_failed")) {
      errors[[length(errors) + 1L]] <- paste0(oid, ".", part, ": ", got$error)
      got <- list(error = got$error)
    }
    value[part] <- list(got)
  }
  list(value = value, errors = errors)
}

#' Collect one output.
#' @noRd
.sashiny_collect_one <- function(engine, oid, spec, main) {
  switch(spec$type,
    table = .sashiny_fetch_table(engine, spec$from, spec$columns,
      as.integer(spec$max_rows %||% 10000L),
      formatted = isTRUE(spec$formatted)
    ),
    chart = .sashiny_fetch_table(engine, spec$from, spec$columns,
      as.integer(spec$max_rows %||% 10000L),
      formatted = FALSE
    ),
    plot = .sashiny_extract_plots(main$LST, spec$select),
    html = main$LST,
    log = .sashiny_scope_log(main$LOG, spec$scope %||% "program"),
    download = .sashiny_fetch_download(engine, oid, spec),
    .sashiny_abort("engine", "unknown output type ", spec$type)
  )
}

#' Read the column metadata and row count of a member (section 8.2, table 1).
#' @noRd
.sashiny_table_meta <- function(engine, lib, mem) {
  sas <- .sashiny_saspy_session(engine)
  .sashiny_submit(engine, .sashiny_table_meta_code(lib, mem))
  cols <- sas$sd2df(table = "_sx_cols", libref = "work")
  ncols <- .sashiny_nrow(cols)
  if (ncols == 0L) {
    .sashiny_abort("engine", sprintf("dataset %s.%s not found", lib, mem))
  }
  nobs <- sas$sd2df(table = "_sx_nobs", libref = "work")
  total <- NULL
  if (.sashiny_nrow(nobs) > 0L) {
    vals <- unlist(nobs[[1]])
    n <- if (length(vals) > 0L) suppressWarnings(as.numeric(vals[[1]])) else NA_real_
    if (!is.na(n)) total <- as.integer(n)
  }
  cell <- function(name, i) unlist(.sashiny_df_column(cols, name)[i])
  meta <- lapply(seq_len(ncols), function(i) {
    type <- tolower(trimws(as.character(cell("type", i))))
    list(
      name = trimws(as.character(cell("name", i))),
      type = if (identical(type, "num")) "numeric" else "character",
      label = .sashiny_text_or_empty(cell("label", i)),
      format = .sashiny_text_or_empty(cell("format", i))
    )
  })
  list(meta = meta, total = total)
}

#' Read a table output (section 8.2, table).
#' @noRd
.sashiny_fetch_table <- function(engine, ref, columns, max_rows, formatted) {
  parts <- .sashiny_split_member(ref)
  lib <- parts$lib
  mem <- parts$mem
  sas <- .sashiny_saspy_session(engine)
  on.exit(try(
    .sashiny_submit(engine, "proc datasets library=work nolist nowarn; delete _sx_:; quit;"),
    silent = TRUE
  ), add = TRUE)
  info <- .sashiny_table_meta(engine, lib, mem)
  chosen <- .sashiny_select_columns(info$meta, columns)
  names <- vapply(chosen, function(m) m$name, character(1))
  if (formatted) {
    .sashiny_submit(engine, .sashiny_formatted_table_code(lib, mem, names, max_rows))
    df <- sas$sd2df(table = "_sx_fmt", libref = "work")
    keys <- paste0("_sx_c", seq_along(names))
  } else {
    df <- sas$sd2df(
      table = mem, libref = lib,
      dsopts = list(obs = as.integer(max_rows), keep = paste(names, collapse = " "))
    )
    keys <- names
  }
  if (is.null(df)) {
    .sashiny_abort("engine", sprintf("could not read %s.%s", lib, mem))
  }
  frame <- lapply(keys, function(k) .sashiny_df_column(df, k))
  rows <- lapply(seq_len(.sashiny_nrow(df)), function(i) {
    lapply(seq_along(chosen), function(j) {
      value <- .sashiny_cell(frame[[j]], i)
      if (!formatted && identical(chosen[[j]]$type, "numeric")) {
        value <- .sashiny_sas_number(value, chosen[[j]]$format)
      }
      value
    })
  })
  .sashiny_build_table(chosen, rows, total_rows = info$total, max_rows = max_rows,
    formatted = formatted
  )
}

#' One cell of a column (list or atomic); NULL when missing.
#' @noRd
.sashiny_cell <- function(column, i) {
  value <- if (is.list(column)) column[[i]] else column[i]
  if (is.null(value) || length(value) == 0L || (is.atomic(value) && is.na(value[[1]]))) {
    return(NULL)
  }
  value
}

#' Turn date/time values back into SAS numbers (section 8.1).
#' @noRd
.sashiny_sas_number <- function(value, fmt) {
  if (is.null(value)) {
    return(NULL)
  }
  upper <- toupper(fmt %||% "")
  is_dt <- grepl("^(DATETIME|DTDATE|E8601DT|B8601DT|IS8601DT|NLDATM|MDYAMPM|DTWKDATX)", upper)
  is_time <- grepl("^(TIME|HHMM|E8601TM|B8601TM|TOD|NLTIME)", upper)
  if (inherits(value, "POSIXt")) {
    secs <- as.numeric(difftime(value, as.POSIXct("1960-01-01", tz = "UTC"), units = "secs"))
    if (is_time) {
      return(secs %% 86400)
    }
    return(if (is_dt) secs else secs / 86400)
  }
  if (inherits(value, "Date")) {
    return(as.numeric(value - as.Date("1960-01-01")))
  }
  if (inherits(value, "difftime")) {
    return(as.numeric(value, units = "secs"))
  }
  value
}

#' Resolve a library's directory on the SAS server.
#' @noRd
.sashiny_remote_dir <- function(engine, libref) {
  log <- .sashiny_submit(engine, sprintf("%%put SASHINY-PATH=%%sysfunc(pathname(%s));", libref))$LOG
  hit <- grep("^SASHINY-PATH=", .sashiny_split_log(log), value = TRUE)
  path <- if (length(hit)) trimws(sub("^SASHINY-PATH=", "", hit[[1]])) else ""
  if (!nzchar(path)) {
    .sashiny_abort("engine", "cannot resolve the path of library ", libref)
  }
  path
}

#' Download a server file and return its bytes.
#' @noRd
.sashiny_fetch_file <- function(engine, remote) {
  dir <- tempfile("sashiny-dl-")
  dir.create(dir)
  on.exit(unlink(dir, recursive = TRUE), add = TRUE)
  local <- file.path(dir, basename(gsub("\\", "/", remote, fixed = TRUE)))
  res <- .sashiny_saspy_session(engine)$download(local, remote)
  if (is.list(res) && !isTRUE(res$Success)) {
    .sashiny_abort("engine", "download failed for ", remote)
  }
  if (!file.exists(local)) {
    .sashiny_abort("engine", "download produced no file for ", remote)
  }
  .sashiny_read_bytes(local)
}

#' Collect a download output (section 8.2, download).
#' @noRd
.sashiny_fetch_download <- function(engine, oid, spec) {
  fmt <- spec$format
  name <- spec$filename %||% oid
  if (fmt %in% c("rtf", "pdf")) {
    remote <- .sashiny_join_remote(
      .sashiny_remote_dir(engine, "work"), sprintf("sashiny_%s.%s", oid, fmt)
    )
    return(.sashiny_download_value(name, fmt, .sashiny_fetch_file(engine, remote)))
  }
  parts <- .sashiny_split_member(spec$from)
  if (identical(fmt, "sas7bdat")) {
    remote <- .sashiny_join_remote(
      .sashiny_remote_dir(engine, parts$lib), paste0(tolower(parts$mem), ".sas7bdat")
    )
    return(.sashiny_download_value(name, fmt, .sashiny_fetch_file(engine, remote)))
  }
  table <- .sashiny_fetch_table(engine, spec$from, NULL, .sashiny_csv_max_rows, formatted = FALSE)
  payload <- switch(fmt,
    csv = .sashiny_csv_bytes(table),
    xlsx = .sashiny_xlsx_bytes(table, parts$mem),
    xpt = .sashiny_xpt_bytes(table, parts$mem),
    .sashiny_abort("engine", "unsupported download format ", fmt)
  )
  .sashiny_download_value(name, fmt, payload)
}
