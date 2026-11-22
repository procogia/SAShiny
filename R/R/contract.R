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
  possessive_quantifier = "[*+?}]\\+"
)

#' Detect an unescaped `^`/`$` outside a character class (spec section 3.3).
#'
#' A `^` or `$` inside `[...]` is not an anchor: `[^x]` is a negated class and
#' `[$]` is a literal dollar sign.
#' @noRd
.sashiny_has_anchor <- function(pattern) {
  chars <- strsplit(pattern, "", fixed = TRUE)[[1]]
  in_class <- FALSE
  i <- 1L
  n <- length(chars)
  while (i <= n) {
    ch <- chars[[i]]
    if (identical(ch, "\\")) {
      i <- i + 2L
      next
    }
    if (identical(ch, "[")) {
      in_class <- TRUE
      i <- i + 1L
      if (i <= n && identical(chars[[i]], "^")) i <- i + 1L
      if (i <= n && identical(chars[[i]], "]")) i <- i + 1L
      next
    }
    if (identical(ch, "]") && in_class) {
      in_class <- FALSE
      i <- i + 1L
      next
    }
    if (ch %in% c("^", "$") && !in_class) {
      return(TRUE)
    }
    i <- i + 1L
  }
  FALSE
}

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
  handlers <- c(list(
    "bool#yes" = bool_yes,
    "bool#no" = bool_no,
    "seq" = function(x) as.list(x)
  ), .sashiny_yaml12_handlers())
  text <- paste(readLines(path, encoding = "UTF-8", warn = FALSE), collapse = "\n")
  data <- yaml::yaml.load(.sashiny_yaml12_tag(text), handlers = handlers)
  structure(
    list(data = data, base_dir = dirname(path), path = path),
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
#' @param error `TRUE` to raise an error of class `sashiny_error_contract`
#'   (naming the contract file and every issue's path) when the contract is
#'   invalid, instead of returning the issues.
#' @return A list of `sashiny_issue` objects (empty when valid); with
#'   `error = TRUE`, the contract, invisibly.
#' @export
sas_validate <- function(contract, today = Sys.Date(), error = FALSE) {
  if (isTRUE(error)) {
    issues <- sas_validate(contract, today)
    if (length(issues)) {
      file <- basename(contract$path %||% "contract")
      details <- vapply(issues, function(i) {
        sprintf("%s %s: %s", i$code, if (nzchar(i$path)) i$path else "(root)", i$message)
      }, character(1))
      .sashiny_abort("contract", sprintf("%s is invalid (%d issue%s):\n", file,
        length(issues), if (length(issues) == 1L) "" else "s"),
        paste0("* ", details, collapse = "\n"),
        .data = list(issues = issues, file = contract$path))
    }
    return(invisible(contract))
  }
  issues <- list()
  validator <- jsonvalidate::json_validator(.sashiny_schema(), engine = "ajv")
    # digits = NA preserves the original numeric values (jsonlite's default
    # rounds to ~15 significant digits, which can turn 1.000001 into 1 and hide
    # a schema type error).
    json <- jsonlite::toJSON(contract$data, auto_unbox = TRUE, null = "null", digits = NA)
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
  if (identical(value, "today")) {
    return(today)
  }
  # Year 0000 is not a real calendar date (spec section 4 V009). R's `as.Date` would
  # otherwise accept it and map it to a "year 0" date.
  if (grepl("^0000-", value)) {
    .sashiny_abort("contract", "year 0000 is not a real calendar date")
  }
  as.Date(value)
}

#' Derive the default module id from a program file name (spec section 2).
#'
#' Take the base name without the `.sas` extension, lower-case it, remove
#' combining marks (so `İ` lower-cases to `i`, not `i` + a combining dot),
#' replace each character outside `[a-z0-9_]` with `_`, prefix `p_` if it does
#' not start with a letter, and truncate to 32 characters.
#' @noRd
.sashiny_default_module_id <- function(program) {
  # Strip the directory with a regex on the UTF-8 form, not basename(), which
  # cannot translate a non-ASCII file name in a C/POSIX locale (issue #99).
  base <- sub(".*[/\\\\]", "", enc2utf8(program))
  if (grepl("\\.sas$", base, ignore.case = TRUE)) {
    base <- substr(base, 1L, nchar(base) - 4L)
  }
  base <- tolower(base)
  # Strip combining marks: every character of general category Mn, Mc or Me,
  # the same set as Python's unicodedata.category(c).startswith("M").
  base <- gsub("\\p{M}", "", base, perl = TRUE)
  base <- gsub("[^a-z0-9_]", "_", base)
  if (!nzchar(base) || !grepl("^[a-z]", base)) {
    base <- paste0("p_", base)
  }
  substr(base, 1L, 32L)
}

#' Resolve a date bound, returning NULL when it is not a real calendar date.
#' @noRd
.sashiny_resolve_bound <- function(value, today) {
  if (is.null(value)) {
    return(NULL)
  }
  tryCatch(.sashiny_resolve_date(value, today), error = function(e) NULL)
}

#' Test whether a value is an integer (numeric with no fractional part).
#' @noRd
.sashiny_is_int <- function(x) {
  is.numeric(x) && length(x) == 1L && is.finite(x) && x == floor(x)
}

#' Check a regex against the portable subset (spec section 3.3).
#' Returns NULL when acceptable, otherwise a description of the problem.
#' @noRd
.sashiny_check_regex <- function(pattern) {
  outside <- .sashiny_outside_class(pattern)
  for (what in names(.sashiny_forbidden_regex)) {
    if (grepl(.sashiny_forbidden_regex[[what]], outside, perl = TRUE)) {
      return(what)
    }
  }
  if (.sashiny_has_anchor(pattern)) {
    return("anchor")
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

#' The pattern with every `[...]` class's contents replaced by spaces.
#'
#' Forbidden constructs are only meaningful outside character classes: a literal
#' `+?` or `(?=` inside `[...]` is not a quantifier or look-around (spec section
#' 3.3). Escaped characters are kept so `\\[` is not mistaken for a class opener.
#' @noRd
.sashiny_outside_class <- function(pattern) {
  chars <- strsplit(pattern, "", fixed = TRUE)[[1]]
  out <- character(length(chars))
  in_class <- FALSE
  i <- 1L
  n <- length(chars)
  while (i <= n) {
    ch <- chars[[i]]
    if (identical(ch, "\\") && i < n) {
      out[[i]] <- ch
      out[[i + 1L]] <- chars[[i + 1L]]
      i <- i + 2L
      next
    }
    if (identical(ch, "[")) {
      in_class <- TRUE
      out[[i]] <- " "
      i <- i + 1L
      next
    }
    if (identical(ch, "]") && in_class) {
      in_class <- FALSE
      out[[i]] <- " "
      i <- i + 1L
      next
    }
    out[[i]] <- if (in_class) " " else ch
    i <- i + 1L
  }
  paste0(out, collapse = "")
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
    if (kind %in% c("date", "daterange") && (!is.null(spec$min) || !is.null(spec$max))) {
          lo <- if (!is.null(spec$min)) .sashiny_resolve_bound(spec$min, today) else NULL
          hi <- if (!is.null(spec$max)) .sashiny_resolve_bound(spec$max, today) else NULL
          # A one-sided bound is valid; only a present-but-invalid bound is S003.
          if ((!is.null(spec$min) && is.null(lo)) || (!is.null(spec$max) && is.null(hi))) {
        add("S003", p, "invalid date bound")
          } else if (!is.null(lo) && !is.null(hi) && lo > hi) {
        add("S003", p, "min > max")
      }
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
        # S017 (generated component ids)
        if (iid %in% c("run", "status", "log") ||
          startsWith(iid, "out_") || startsWith(iid, "dl_") ||
          endsWith(iid, "__sample")) {
          add("S017", p, "id collides with a generated module component id")
        }
    # S013 (sample)
    if (identical(kind, "dataset") && !is.null(spec$sample) &&
      !utils::file_test("-f", file.path(contract$base_dir, spec$sample))) {
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
  if (!utils::file_test("-f", file.path(contract$base_dir, d$program))) {
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

# ---------------------------------------------------------------------------
# YAML 1.2 core numbers (spec section 1.1)

#' YAML 1.2 core schema integer pattern (spec section 1.1).
#'
#' No `_` separators, no sexagesimal, no leading-zero octal (`010` is 10) and
#' no `0b`; `0o17`, `0x1F`, `1e5` and `-.5` are numbers.
#' @noRd
.sashiny_yaml12_int <- "^(?:[-+]?[0-9]+|0o[0-7]+|0x[0-9a-fA-F]+)$"

#' YAML 1.2 core schema float pattern (spec section 1.1).
#' @noRd
.sashiny_yaml12_float <- paste0(
  "^(?:[-+]?(?:\\.[0-9]+|[0-9]+(?:\\.[0-9]*)?)(?:[eE][-+]?[0-9]+)?",
  "|[-+]?\\.(?:inf|Inf|INF)|\\.(?:nan|NaN|NAN))$"
)

#' The YAML 1.2 core number a plain scalar denotes, or `NULL`.
#'
#' Integers within R's integer range are returned as integers, other numbers
#' as doubles.
#' @param x The scalar text.
#' @noRd
.sashiny_yaml12_number <- function(x) {
  if (grepl(.sashiny_yaml12_int, x, perl = TRUE)) {
    value <- if (startsWith(x, "0o")) {
      .sashiny_parse_base(substring(x, 3L), 8)
    } else if (startsWith(x, "0x")) {
      .sashiny_parse_base(substring(x, 3L), 16)
    } else {
      as.numeric(x)
    }
    if (abs(value) <= .Machine$integer.max) value <- as.integer(value)
    return(value)
  }
  if (grepl(.sashiny_yaml12_float, x, perl = TRUE)) {
    low <- tolower(x)
    if (endsWith(low, ".nan")) {
      return(NaN)
    }
    if (endsWith(low, ".inf")) {
      return(if (startsWith(low, "-")) -Inf else Inf)
    }
    return(as.numeric(x))
  }
  NULL
}

#' Parse unsigned base-8 or base-16 digits as a double (no integer overflow).
#' @noRd
.sashiny_parse_base <- function(digits, base) {
  d <- match(strsplit(tolower(digits), "")[[1]], c(0:9, letters[1:6])) - 1
  Reduce(function(acc, v) acc * base + v, d, 0)
}

#' 'yaml' handlers that re-resolve numbers by the YAML 1.2 core schema.
#'
#' The 'yaml' package resolves numbers by YAML 1.1 rules. Every scalar it types
#' as a number is checked again: a YAML 1.2 number is converted, anything else
#' (`1,000`, `190:20:30`, `+0x1F`) stays a string, as in Python.
#' @noRd
.sashiny_yaml12_handlers <- function() {
  as_number <- function(x) .sashiny_yaml12_number(x) %||% x
  as_double <- function(x) {
    n <- .sashiny_yaml12_number(x)
    if (is.null(n)) x else as.double(n)
  }
  ints <- c("int", "int#hex", "int#oct", "int#base60")
  floats <- c("float", "float#fix", "float#exp", "float#base60", "float#inf", "float#neginf", "float#nan")
  c(
    stats::setNames(rep(list(as_number), length(ints)), ints),
    stats::setNames(rep(list(as_double), length(floats)), floats)
  )
}

#' Tag plain YAML 1.2 numbers that the 'yaml' package would read as strings.
#'
#' The 'yaml' package leaves `0o17`, `1e5` and `1.0e5` untyped, and its string
#' handler cannot tell a plain scalar from a quoted one. This pre-pass marks
#' each *plain* number scalar with an explicit `!!int`/`!!float` tag, so the
#' handlers above convert it, while quoted scalars stay strings. It covers
#' block mapping values, block sequence items and single-line flow collections
#' without quotes; text inside block scalars (`|`, `>`) is left alone.
#' @param text The contract text.
#' @noRd
.sashiny_yaml12_tag <- function(text) {
  lines <- strsplit(text, "\n", fixed = TRUE)[[1]]
  tag_of <- function(tok) {
    if (grepl(.sashiny_yaml12_int, tok, perl = TRUE)) {
      "!!int "
    } else if (grepl(.sashiny_yaml12_float, tok, perl = TRUE)) {
      "!!float "
    } else {
      ""
    }
  }
  key <- "(?:[^\\s'\"#?:,\\[\\]{}|>!&*%@`-][^#]*?|\"[^\"]*\"|'[^']*')"
  lead <- paste0("^(\\s*(?:-\\s+)*(?:", key, ":\\s+)?)")
  block_re <- paste0(lead, "([^\\s'\"#,\\[\\]{}!&*|>]+)(\\s*(?:#.*)?)$")
  quoted <- "\"(?:[^\"\\\\]|\\\\.)*\"|'(?:[^']|'')*'"
  flow_re <- paste0(lead, "([\\[{](?:", quoted, "|[^'\"#])*[\\]}])(\\s*(?:#.*)?)$")
  block_scalar_re <- paste0(lead, "[|>][-+0-9]*\\s*(?:#.*)?$")
  block_parent <- NA_integer_
  for (i in seq_along(lines)) {
    line <- sub("\r$", "", lines[[i]])
    indent <- nchar(line) - nchar(sub("^ +", "", line))
    if (!is.na(block_parent)) {
      if (!nzchar(trimws(line)) || indent > block_parent) next
      block_parent <- NA_integer_
    }
    if (grepl(block_scalar_re, line, perl = TRUE)) {
      block_parent <- indent
      next
    }
    m <- regmatches(line, regexec(block_re, line, perl = TRUE))[[1]]
    if (length(m) == 4L) {
      tag <- tag_of(m[[3]])
      if (nzchar(tag)) lines[[i]] <- paste0(m[[2]], tag, m[[3]], m[[4]])
      next
    }
    m <- regmatches(line, regexec(flow_re, line, perl = TRUE))[[1]]
    if (length(m) == 4L) {
      # Split the flow collection into its scalars and tag each plain number.
      pieces <- regmatches(m[[3]], gregexpr(
        # A `:` separates a key only when a blank follows it (`190:20:30` is one scalar).
        paste0(quoted, "|(?:[^\\[\\]{},:\\s'\"]|:(?!\\s))+|(?:[\\[\\]{},\\s]|:(?=\\s))+"), m[[3]],
        perl = TRUE
      ))[[1]]
      tokens <- !grepl("^((?:[\\[\\]{},\\s]|:(?=\\s|$))+|[\"'].*)$", pieces, perl = TRUE)
      pieces[tokens] <- vapply(pieces[tokens], function(t) paste0(tag_of(t), t), "")
      lines[[i]] <- paste0(m[[2]], paste(pieces, collapse = ""), m[[4]])
    }
  }
  paste(lines, collapse = "\n")
}
