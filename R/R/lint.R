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

# A `%symexist(NAME)` guard reference.
.sashiny_symexist_re <- "%symexist\\s*\\(\\s*([A-Za-z_][A-Za-z0-9_]*)\\s*\\)"

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

# Upper-cased macro names referenced by a `%symexist` guard.
.sashiny_guarded_names <- function(program_text) {
  m <- gregexpr(.sashiny_symexist_re, program_text, perl = TRUE, ignore.case = TRUE)[[1]]
  if (m[1] == -1L) {
    return(character())
  }
  starts <- attr(m, "capture.start")
  lens <- attr(m, "capture.length")
  vapply(seq_along(m), function(i) {
    toupper(substr(program_text, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L))
  }, character(1))
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
  guarded <- .sashiny_guarded_names(text)

  # L001: program assigns an injected macro outside a %symexist guard.
  for (name in injected) {
    if (name %in% assigned && !(name %in% guarded)) {
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
