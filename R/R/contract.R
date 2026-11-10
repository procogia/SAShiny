# Contract loading and validation for SAShiny.
#
# Implements spec/CONTRACT.md sections 1-3: safe YAML loading (no timestamp
# typing), JSON Schema 2020-12 validation (E000) and the semantic rules
# S001-S016. Every error is reported with a code, a JSON-pointer-style path and
# a message.
#
# This is the R equivalent of the reference oracle spec/tools/sashiny_ref.py
# and must behave identically.

# Reserved macro-name prefixes (spec section 3.2 S002).
.sashiny_reserved <- "^SYS|^SASHINY|^_SX_"
.sashiny_sas_name <- "^[A-Za-z_][A-Za-z0-9_]{0,31}$"
.sashiny_numeric_literal <- "^-?(\\d+\\.?\\d*|\\.\\d+)([Ee][+-]?\\d+)?$"

# Portable regex subset (spec section 3.3): constructs outside the subset.
.sashiny_forbidden_regex <- list(
  lookaround = "\\(\\?[=!<]",
  named_group = "\\(\\?P?<",
  inline_flag = "\\(\\?[a-zA-Z]",
  backreference = "\\\\[1-9]",
  unicode_prop = "\\\\[pPkK]",
  lazy_quantifier = "[*+?}]\\?",
  possessive_quantifier = "[*+?}]\\+",
  anchor = "(?<!\\\\)[\\^$]"
)

#' A single validation issue
#'
#' @param code Error code (`E000`, `S001`-`S016`).
#' @param path JSON-pointer-style path to the offending value.
#' @param message Human-readable detail.
#' @return A `sashiny_issue` object (a named list).
#' @noRd
sashiny_issue <- function(code, path, message = "") {
  structure(
    list(code = code, path = path, message = message),
    class = "sashiny_issue"
  )
}

#' Load a contract YAML file with a safe loader
#'
#' Reads the contract with `yaml::read_yaml`, which does not coerce ISO dates
#' to `Date` objects (spec section 1.1). Boolean handling is adjusted to match
#' PyYAML: single letters `y`/`Y`/`n`/`N` stay strings, while the full words
#' (`yes`, `no`, `on`, `off`, `true`, `false`) become logicals. Returns a
#' `sashiny_contract` object holding the parsed data and the file's directory.
#'
#' @param path Path to the `*.sashiny.yml` file.
#' @return A `sashiny_contract` object.
#' @examples
#' # A minimal contract in a temporary directory.
#' dir <- tempfile("sashiny-")
#' dir.create(dir)
#' writeLines(c(
#'   "sashiny: 1",
#'   "program: program.sas",
#'   "title: Minimal",
#'   "outputs:",
#'   "  log:",
#'   "    type: log"
#' ), file.path(dir, "contract.sashiny.yml"))
#' writeLines("proc print data=sashelp.class; run;", file.path(dir, "program.sas"))
#' contract <- sas_contract(file.path(dir, "contract.sashiny.yml"))
#' sas_validate(contract)
#' @export
sas_contract <- function(path) {
  path <- normalizePath(path, mustWork = TRUE)
  # Match PyYAML's boolean handling (spec section 1.1): single letters stay
  # strings, full words become logicals.
  bool_yes <- function(x) if (tolower(x) %in% c("y", "n")) x else TRUE
  bool_no <- function(x) if (tolower(x) %in% c("y", "n")) x else FALSE
  # Preserve sequences as lists (matching PyYAML, which keeps arrays distinct
  # from scalars).
  handlers <- list(
    "bool#yes" = bool_yes,
    "bool#no" = bool_no,
    "seq" = function(x) as.list(x)
  )
  data <- yaml::read_yaml(path, handlers = handlers)
  structure(
    list(data = data, base_dir = dirname(path)),
    class = "sashiny_contract"
  )
}

#' Validate a contract
#'
#' Validates the contract against the JSON Schema (E000) and the semantic rules
#' (S001-S016), returning every issue found.
#'
#' @param contract A `sashiny_contract` object from [sas_contract()].
#' @param today A `Date` used to resolve `"today"` in date bounds. Defaults to
#'   the current date.
#' @return A list of `sashiny_issue` objects (empty when valid).
#' @export
sas_validate <- function(contract, today = Sys.Date()) {
  issues <- list()
  validator <- jsonvalidate::json_validator(.sashiny_schema(), engine = "ajv")
  json <- jsonlite::toJSON(contract$data, auto_unbox = TRUE, null = "null")
  result <- validator(json, verbose = TRUE, error = FALSE)
  if (isTRUE(result)) {
    schema_errors <- NULL
  } else {
    schema_errors <- attr(result, "errors")
  }
  if (!is.null(schema_errors) && nrow(schema_errors) > 0L) {
    for (i in seq_len(nrow(schema_errors))) {
      err <- schema_errors[i, , drop = FALSE]
      pointer <- err$instancePath %||% err$dataPath %||% ""
      issues[[length(issues) + 1L]] <- sashiny_issue("E000", pointer, err$message %||% "")
    }
  }
  if (length(issues) > 0L) {
    # Semantic checks assume a structurally valid document.
    return(issues)
  }
  c(issues, .sashiny_semantic(contract, today))
}

# ---------------------------------------------------------------------------
# helpers

#' Macro names set by one input, upper-cased, in spec section 5.7 order.
#' @noRd
.sashiny_macro_names <- function(input_id, spec) {
  kind <- spec$type
  if (identical(kind, "dataset")) {
    if (!is.null(spec$macro)) {
      return(toupper(spec$macro))
    }
    return(character())
  }
  if (identical(kind, "daterange")) {
    names <- spec$macro %||% c(paste0(input_id, "_start"), paste0(input_id, "_end"))
    return(toupper(unlist(names, use.names = FALSE)))
  }
  names <- toupper(spec$macro %||% input_id)
  if (identical(kind, "multichoice") && !is.null(spec$count_macro)) {
    names <- c(names, toupper(spec$count_macro))
  }
  names
}

#' All macro names a contract can set, in contract order.
#' @noRd
.sashiny_all_macro_names <- function(data) {
  out <- character()
  for (iid in names(data$inputs %||% list())) {
    out <- c(out, .sashiny_macro_names(iid, data$inputs[[iid]]))
  }
  out
}

#' Static choice values, or NULL when `choices_from` is used.
#' @noRd
.sashiny_choice_values <- function(spec) {
  if (!"choices" %in% names(spec)) {
    return(NULL)
  }
  vapply(spec[["choices"]], function(c) {
    if (is.character(c)) c else c$value
  }, character(1))
}

#' Resolve a date value, mapping "today" to `today`.
#' @noRd
.sashiny_resolve_date <- function(value, today) {
  if (identical(value, "today")) today else as.Date(value)
}

#' Test whether a value is an integer (numeric with no fractional part).
#' @noRd
.sashiny_is_int <- function(x) {
  is.numeric(x) && !is.logical(x) && x == floor(x)
}

#' Check a regex against the portable subset (spec section 3.3).
#' Returns NULL when acceptable, otherwise a description of the problem.
#' @noRd
.sashiny_check_regex <- function(pattern) {
  for (what in names(.sashiny_forbidden_regex)) {
    if (grepl(.sashiny_forbidden_regex[[what]], pattern, perl = TRUE)) {
      return(what)
    }
  }
  ok <- tryCatch(
    {
      grepl(pattern, "", perl = TRUE)
      TRUE
    },
    error = function(e) FALSE
  )
  if (!ok) {
    return("does not compile")
  }
  NULL
}

# ---------------------------------------------------------------------------
# semantic layer (spec section 3.2)

.sashiny_semantic <- function(contract, today) {
  d <- contract$data
  inputs <- d$inputs %||% list()
  outputs <- d$outputs
  issues <- list()

  add <- function(code, path, message = "") {
    issues[[length(issues) + 1L]] <<- sashiny_issue(code, path, message)
  }

  # S001 / S002
  seen <- list()
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    for (name in .sashiny_macro_names(iid, spec)) {
      if (!is.null(seen[[name]])) {
        add("S001", paste0("/inputs/", iid), paste0("macro ", name, " also set by ", seen[[name]]))
      } else {
        seen[[name]] <- iid
      }
    }
    explicit <- !is.null(spec$macro)
    if (!(spec$type %in% c("dataset", "daterange")) && !explicit &&
      grepl(.sashiny_reserved, iid, ignore.case = TRUE)) {
      add("S002", paste0("/inputs/", iid), "default macro name is reserved")
    }
    if (identical(spec$type, "daterange") && !explicit &&
      grepl(.sashiny_reserved, iid, ignore.case = TRUE)) {
      add("S002", paste0("/inputs/", iid), "default macro names are reserved")
    }
  }

  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    p <- paste0("/inputs/", iid)
    kind <- spec$type
    # S003
    if (identical(kind, "numeric") && !is.null(spec$min) && !is.null(spec$max) &&
      spec$min > spec$max) {
      add("S003", p, "min > max")
    }
    if (kind %in% c("date", "daterange") && !is.null(spec$min) && !is.null(spec$max) &&
      .sashiny_resolve_date(spec$min, today) > .sashiny_resolve_date(spec$max, today)) {
      add("S003", p, "min > max")
    }
    # S005
    vals <- .sashiny_choice_values(spec)
    if (!is.null(vals) && length(unique(vals)) != length(vals)) {
      add("S005", paste0(p, "/choices"), "duplicate choice values")
    }
    # S006
    if (identical(kind, "multichoice")) {
      lo <- spec$min_selected %||% 1L
      hi <- spec$max_selected
      if (!is.null(hi) && lo > hi) {
        add("S006", p, "min_selected > max_selected")
      }
      if (!is.null(vals) && (lo > length(vals) || (!is.null(hi) && hi > length(vals)))) {
        add("S006", p, "selection bounds exceed number of choices")
      }
      # S007
      bad_bare <- !is.null(vals) && any(!grepl(.sashiny_sas_name, vals) &
        !grepl(.sashiny_numeric_literal, vals))
      if (identical(spec$render, "bare") && bad_bare) {
        add("S007", paste0(p, "/choices"), "bare render needs SAS names or numbers")
      }
    }
    # S014
    if (identical(kind, "text") && !is.null(spec$pattern)) {
      problem <- .sashiny_check_regex(spec$pattern)
      if (!is.null(problem)) {
        add("S014", paste0(p, "/pattern"), problem)
      }
    }
    # S015
    if (identical(kind, "numeric") && isTRUE(spec$integer)) {
      for (k in c("min", "max", "default")) {
        if (!is.null(spec[[k]]) && !.sashiny_is_int(spec[[k]])) {
          add("S015", paste0(p, "/", k), "must be an integer")
        }
      }
    }
    # S016
    if (identical(kind, "dataset") && !is.null(spec$columns)) {
      names <- toupper(vapply(spec$columns, function(c) c$name, character(1)))
      if (length(unique(names)) != length(names)) {
        add("S016", paste0(p, "/columns"), "duplicate column names")
      }
    }
    # S013 (sample)
    if (identical(kind, "dataset") && !is.null(spec$sample) &&
      !file.exists(file.path(contract$base_dir, spec$sample))) {
      add("S013", paste0(p, "/sample"), "sample file not found")
    }
    # S004
    if (!is.null(spec$default) && !identical(kind, "dataset")) {
      default <- spec$default
      if (kind %in% c("date", "daterange")) {
        iso <- format(today, "%Y-%m-%d")
        if (is.list(default)) {
          default <- lapply(default, function(x) if (identical(x, "today")) iso else x)
        } else if (identical(default, "today")) {
          default <- iso
        }
      }
      errs <- .sashiny_render_values_for_default(d, stats::setNames(list(default), iid), today, only = iid)
      for (e in errs$issues) {
        add("S004", paste0(p, "/default"), e$code)
      }
    }
  }

  # S008
  for (oid in names(outputs)) {
    spec <- outputs[[oid]]
    if (identical(spec$type, "download")) {
      if (spec$format %in% c("csv", "xlsx", "xpt", "sas7bdat") && is.null(spec$from)) {
        add("S008", paste0("/outputs/", oid), "data download needs 'from'")
      }
      if (spec$format %in% c("rtf", "pdf") && !is.null(spec$from)) {
        add("S008", paste0("/outputs/", oid), "ODS download must not have 'from'")
      }
    }
  }
  # S009
  run <- d$run %||% list()
  if (identical(run$entry, "macro") && is.null(run$macro)) {
    add("S009", "/run", "entry: macro requires run.macro")
  }
  if (!is.null(run$macro) && !identical(run$entry, "macro")) {
    add("S009", "/run/macro", "run.macro requires entry: macro")
  }
  # S010
  targets <- list()
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    if (identical(spec$type, "dataset")) {
      t <- toupper(spec$target)
      if (!is.null(targets[[t]])) {
        add("S010", paste0("/inputs/", iid, "/target"), paste0("target also used by ", targets[[t]]))
      }
      targets[[t]] <- iid
    }
  }
  # S011
  for (oid in names(outputs)) {
    if (oid %in% names(inputs)) {
      add("S011", paste0("/outputs/", oid), "id collides with an input id")
    }
  }
  # S012
  order <- (d$ui %||% list())$order %||% character()
  for (i in seq_along(order)) {
    if (!(order[[i]] %in% names(inputs))) {
      add("S012", paste0("/ui/order/", i - 1L), paste0("unknown input ", order[[i]]))
    }
  }
  # S013 (program)
  if (!file.exists(file.path(contract$base_dir, d$program))) {
    add("S013", "/program", "program file not found")
  }
  issues
}

# ---------------------------------------------------------------------------
# schema

#' Load the bundled JSON Schema.
#' @noRd
.sashiny_schema <- function() {
  path <- system.file("spec", "sashiny.schema.json", package = "SAShiny")
  if (!nzchar(path)) {
    # Development fallback: read from the repo's spec/ directory.
    path <- file.path("..", "spec", "sashiny.schema.json")
  }
  path
}

# ---------------------------------------------------------------------------
# value rendering (delegated to values.R)

.sashiny_render_values_for_default <- function(data, values, today, only) {
  sas_render_values(data, values, today, only = only)
}
