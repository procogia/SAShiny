# Advisory lint for SAShiny (spec section 10).
#
# Reports program-vs-contract consistency findings (L001-L005). These are
# advisory, not errors. The implementation scans the SAS program text with
# conservative, case-insensitive regular expressions; it deliberately avoids a
# full SAS parser and prefers to miss a finding over raising a false positive.

# A `%let NAME = ...;` assignment (NAME captured, case-insensitive).
.sashiny_let_re <- "%let\\s+([A-Za-z_][A-Za-z0-9_]*)\\s*="

# A `call symput('NAME', ...)` or `call symputx('NAME', ...)` assignment.
.sashiny_symput_re <- "call\\s+symputx?\\s*\\(\\s*['\"]([A-Za-z_][A-Za-z0-9_]*)['\"]"

# A `%if not %symexist(NAME) %then %do;` guard opening (NAME captured).
.sashiny_guard_open_re <- "%if\\s+not\\s+%symexist\\s*\\(\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*\\)\\s*%then\\s*%do\\s*;"

# A `%end;` closing a guard block.
.sashiny_guard_close_re <- "%end\\s*;"

# Upper-cased macro names assigned via `%let` or `call symput[x]`.
.sashiny_assigned_names <- function(program_text) {
  names <- character()
  m <- gregexpr(.sashiny_let_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (m[1] != -1L) {
    starts <- attr(m, "capture.start")
    lens <- attr(m, "capture.length")
    for (i in seq_along(m)) {
      names <- c(names, toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L)))
    }
  }
  m <- gregexpr(.sashiny_symput_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (m[1] != -1L) {
    starts <- attr(m, "capture.start")
    lens <- attr(m, "capture.length")
    for (i in seq_along(m)) {
      names <- c(names, toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L)))
    }
  }
  unique(names)
}

# `(upper_name, start_offset)` for every macro assignment (`%let`/`symput[x]`).
.sashiny_assignment_positions <- function(program_text) {
  out <- list()
  m <- gregexpr(.sashiny_let_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (m[1] != -1L) {
    starts <- attr(m, "capture.start")
    lens <- attr(m, "capture.length")
    for (i in seq_along(m)) {
      name <- toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L))
      out[[length(out) + 1L]] <- list(name = name, pos = m[i])
    }
  }
  m <- gregexpr(.sashiny_symput_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (m[1] != -1L) {
    starts <- attr(m, "capture.start")
    lens <- attr(m, "capture.length")
    for (i in seq_along(m)) {
      name <- toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L))
      out[[length(out) + 1L]] <- list(name = name, pos = m[i])
    }
  }
  out
}

# `(upper_name, start, end)` for each `%if not %symexist(NAME) %then %do; ... %end;`
# guard. An unmatched opening is ignored (a conservative miss is preferred).
.sashiny_guard_ranges <- function(program_text) {
  out <- list()
  opens <- gregexpr(.sashiny_guard_open_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (opens[1] == -1L) {
    return(out)
  }
  starts <- attr(opens, "capture.start")
  lens <- attr(opens, "capture.length")
  closes <- gregexpr(.sashiny_guard_close_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  for (i in seq_along(opens)) {
    name <- toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L))
    open_end <- opens[i] + attr(opens, "match.length")[i]
    after <- closes[closes >= open_end]
    if (length(after) == 0L) {
      next
    }
    close_end <- after[[1]] + attr(closes, "match.length")[which(closes == after[[1]])[1]]
    out[[length(out) + 1L]] <- list(name = name, start = opens[i], end = close_end)
  }
  out
}

# Upper-cased WORK member names that dataset inputs target.
.sashiny_dataset_targets <- function(data) {
  targets <- character()
  for (spec in data$inputs %||% list()) {
    if (identical(spec$type, "dataset") && !is.null(spec$target)) {
      targets <- c(targets, toupper(spec$target))
    }
  }
  unique(targets)
}

# The input id that sets `name`, or `name` lower-cased.
.sashiny_input_id_for_macro <- function(data, name) {
  for (iid in names(data$inputs %||% list())) {
    one <- stats::setNames(list(data$inputs[[iid]]), iid)
    if (name %in% .sashiny_all_macro_names(list(inputs = one))) {
      return(iid)
    }
  }
  tolower(name)
}

#' Lint a contract against its program text
#'
#' Returns advisory findings (L001-L005) by scanning the SAS program text with
#' conservative, case-insensitive regular expressions.
#'
#' @param data The parsed contract data (a list).
#' @param program_text The decoded SAS program text.
#' @return A list of `sashiny_issue` objects with `L0xx` codes.
#' @export
sashiny_lint <- function(data, program_text) {
  issues <- list()
  text <- program_text %||% ""

  injected <- .sashiny_all_macro_names(data)
  assigned <- .sashiny_assigned_names(text)

    # L001: program assigns an injected macro outside a %symexist guard. The
    # guard exemption applies only to assignments inside the guard (spec §10);
    # a later assignment to the same macro outside any guard is still L001.
    positions <- .sashiny_assignment_positions(text)
    guards <- .sashiny_guard_ranges(text)
  for (name in injected) {
      if (!(name %in% assigned)) {
        next
      }
      flagged <- FALSE
      for (a in positions) {
        if (!identical(a$name, name)) {
          next
        }
        inside <- FALSE
        for (g in guards) {
          if (identical(g$name, name) && a$pos >= g$start && a$pos < g$end) {
            inside <- TRUE
            break
          }
        }
        if (!inside) {
          flagged <- TRUE
          break
        }
      }
      if (flagged) {
      issues[[length(issues) + 1L]] <- sashiny_issue(
        "L001",
        paste0("/inputs/", .sashiny_input_id_for_macro(data, name)),
        sprintf("macro %s is assigned in the program outside a %%symexist guard", name)
      )
    }
  }

  # L002: injected macro never referenced.
  for (name in injected) {
    ref_re <- paste0("&", name, "\\b")
    if (!grepl(ref_re, text, perl = TRUE, ignore.case = TRUE)) {
      issues[[length(issues) + 1L]] <- sashiny_issue(
        "L002",
        paste0("/inputs/", .sashiny_input_id_for_macro(data, name)),
        sprintf("macro %s is never referenced in the program", name)
      )
    }
  }

  # L003: table/download `from` dataset never created and not a target.
  targets <- .sashiny_dataset_targets(data)
  for (oid in names(data$outputs %||% list())) {
    spec <- data$outputs[[oid]]
    if (!(spec$type %in% c("table", "download"))) {
      next
    }
    ref <- spec$from
    if (is.null(ref) || !grepl(".", ref, fixed = TRUE)) {
      next
    }
    parts <- strsplit(ref, ".", fixed = TRUE)[[1]]
    lib <- toupper(parts[[1]])
    member <- toupper(parts[[2]])
    if (!identical(lib, "WORK")) {
      next
    }
    if (member %in% targets) {
      next
    }
    if (grepl(paste0("\\b", member, "\\b"), text, perl = TRUE, ignore.case = TRUE)) {
      next
    }
    issues[[length(issues) + 1L]] <- sashiny_issue(
      "L003",
      paste0("/outputs/", oid),
      sprintf("dataset %s is never created in the program", ref)
    )
  }

  # L004: more than one rtf/pdf download.
  rtf_pdf <- character()
  for (oid in names(data$outputs %||% list())) {
    spec <- data$outputs[[oid]]
    if (identical(spec$type, "download") &&
      tolower(spec$format %||% "") %in% c("rtf", "pdf")) {
      rtf_pdf <- c(rtf_pdf, oid)
    }
  }
  if (length(rtf_pdf) > 1) {
    issues[[length(issues) + 1L]] <- sashiny_issue(
      "L004",
      "/outputs",
      "more than one rtf/pdf download; each receives the same output"
    )
  }

  # L005: entry: macro but %macro <MACRO> not found.
  run <- data$run %||% list()
  if (identical(run$entry, "macro")) {
    macro <- run$macro
    if (!is.null(macro) &&
      !grepl(paste0("%macro\\s+", macro, "\\b"), text, perl = TRUE, ignore.case = TRUE)) {
      issues[[length(issues) + 1L]] <- sashiny_issue(
        "L005",
        "/run/macro",
        sprintf("%%macro %s not found in the program", macro)
      )
    }
  }

    # A daterange or multichoice input sets several macro names that all map to
    # the same input id, so the same (code, path) can be reported more than once.
    # Deduplicate by (code, path) while preserving first-seen order.
    if (length(issues) > 0L) {
      keys <- vapply(issues, function(i) paste(i$code, i$path, sep = "\r"), character(1))
      issues <- issues[!duplicated(keys)]
    }

  issues
}
