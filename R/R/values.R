# Value validation and rendering for SAShiny.
#
# Implements spec/CONTRACT.md sections 4-5: value validation (V001-V014) and
# the rendering of validated values into the logical text of each macro
# variable. Rendering is exact and specified; nothing here needs SAS-escaping
# (that happens in wrapper.R).

.sashiny_sas_epoch <- as.Date("1960-01-01")
.sashiny_months <- c(
  "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
  "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"
)
# Control characters U+0000-U+001F and U+007F-U+009F (spec section 4 V007).
# Written as literal \xNN escapes (PCRE), since R source cannot contain NUL.
.sashiny_control <- "[\\x00-\\x1f\\x7f-\\x9f]"
.sashiny_max_macro_bytes <- 32000L
# Integers with absolute value below this are written without exponent (spec 5.1).
.sashiny_integer_plain_limit <- 1e15

# Unicode White_Space characters used for trimming text values (spec section 4).
.sashiny_ws <- paste0(
  "\t\n\v\f\r \u0085\u00a0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006",
  "\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)

#' Macro names that need `%superq` (spec section 6.3)
#'
#' Only `raw` text/choice values need macro quoting, because they are unquoted
#' and could contain live `&` or `%`. Quoted, dquoted, numeric, date, multichoice,
#' dataset, and validated-bare values are already inert (SAS string literals or
#' SAS names/numeric literals), so they are emitted directly.
#' @noRd
.sashiny_superq_macros <- function(data) {
  out <- character()
  for (iid in names(data$inputs %||% list())) {
    spec <- data$inputs[[iid]]
    if (spec$type %in% c("text", "choice") && identical(spec$render %||% "raw", "raw")) {
      out <- c(out, .sashiny_macro_names(iid, spec))
    }
  }
  out
}

#' Render a numeric value (spec section 5.1)
#' @noRd
.sashiny_render_number <- function(x) {
  if (x == 0) {
    return("0")
  }
  if (x == floor(x) && abs(x) < .sashiny_integer_plain_limit) {
    return(sprintf("%.0f", x))
  }
  out <- sprintf("%.15g", x)
  toupper(out)
}

#' Render a text/choice value (spec section 5.2)
#' @noRd
.sashiny_render_text <- function(v, mode) {
  if (identical(mode, "quoted")) {
    return(paste0("'", gsub("'", "''", v, fixed = TRUE), "'"))
  }
  if (identical(mode, "dquoted")) {
    return(paste0('"', gsub('"', '""', v, fixed = TRUE), '"'))
  }
  v
}

#' Render a date value (spec section 5.4)
#' @noRd
.sashiny_render_date <- function(dt, mode) {
  if (identical(mode, "date9")) {
    return(sprintf(
      "%02d%s%04d", as.integer(format(dt, "%d")),
      .sashiny_months[as.integer(format(dt, "%m"))],
      as.integer(format(dt, "%Y"))
    ))
  }
  if (identical(mode, "iso")) {
      # format(dt, "%Y-%m-%d") drops zero-padding for years below 1000 on some
      # platforms (e.g. "1-01-01"); render the four-digit year explicitly.
      return(sprintf(
        "%04d-%02d-%02d",
        as.integer(format(dt, "%Y")),
        as.integer(format(dt, "%m")),
        as.integer(format(dt, "%d"))
      ))
  }
  if (identical(mode, "sasdate")) {
    return(as.character(as.integer(difftime(dt, .sashiny_sas_epoch, units = "days"))))
  }
  sprintf(
    "'%02d%s%04d'd", as.integer(format(dt, "%d")),
    .sashiny_months[as.integer(format(dt, "%m"))],
    as.integer(format(dt, "%Y"))
  )
}

#' Trim Unicode White_Space from both ends of a string.
#' @noRd
.sashiny_ws_strip <- function(v) {
  sub(
    paste0("^[", .sashiny_ws, "]+"), "",
    sub(paste0("[", .sashiny_ws, "]+$"), "", v)
  )
}

#' Validate and render values
#'
#' Validates input values (V001-V014) and renders them into the logical text of
#' each macro variable (spec sections 4-5).
#'
#' @param data The parsed contract data (a list).
#' @param values A named list of input values keyed by input id.
#' @param today A `Date` used to resolve `"today"`.
#' @param only When given, restrict processing to these input ids.
#' @param choices_override A named list of choices read from SAS for
#'   `choices_from` inputs.
#' @param uploads A named list mapping dataset input ids to `TRUE` when a file
#'   was supplied.
#' @return A list with `macros` (a named list in spec section 5.7 order) and
#'   `issues` (a list of `sashiny_issue` objects).
#' @export
sas_render_values <- function(data, values, today = Sys.Date(), only = NULL,
                              choices_override = NULL, uploads = NULL) {
  inputs <- data$inputs %||% list()
  uploads <- uploads %||% list()
  macros <- list()
  issues <- list()

  add <- function(code, path, message = "") {
    issues[[length(issues) + 1L]] <<- sashiny_issue(code, path, message)
  }

  if (is.null(only)) {
    for (k in names(values)) {
      if (!(k %in% names(inputs))) {
        add("V011", k)
      }
    }
  }

  for (iid in names(inputs)) {
    if (!is.null(only) && !(iid %in% only)) {
      next
    }
    spec <- inputs[[iid]]
    kind <- spec$type
    names <- .sashiny_macro_names(iid, spec)
    raw <- values[[iid]]

    # Normalise JSON arrays (lists) to character vectors for list-valued inputs.
    # A scalar (non-list) value for these types is a type error (V002).
    if (kind %in% c("multichoice", "daterange") && !is.null(raw) && !is.list(raw)) {
      add("V002", iid)
      next
    }
    if (kind %in% c("multichoice", "daterange") && is.list(raw)) {
          # A JSON object (named list) is not an array (spec §2.1): V002.
          if (!is.null(names(raw))) {
            add("V002", iid)
            next
          }
          # A daterange must be exactly two elements (spec §2.1): V002 otherwise.
          if (identical(kind, "daterange") && length(raw) != 2L) {
            add("V002", iid)
            next
          }
          # Every element must be a string (spec §2.1). A nested list, NULL or
          # non-string element is a type error (V002), not silently flattened.
          if (length(raw) > 0L && !all(vapply(raw, is.character, logical(1)))) {
            add("V002", iid)
            next
          }
      raw <- if (length(raw) == 0L) character() else unlist(raw, use.names = FALSE)
    }

    if (identical(kind, "dataset")) {
      present <- isTRUE(uploads[[iid]])
      if (!present && !isTRUE(spec$optional)) {
        add("V001", iid)
        next
      }
      for (n in names) {
        macros[[n]] <- if (present) toupper(spec$target) else ""
      }
      next
    }

    if (is.character(raw) && identical(kind, "text")) {
      raw <- .sashiny_ws_strip(raw)
    }
    optional <- isTRUE(spec$optional)

    if (identical(kind, "multichoice")) {
          if (is.null(raw)) {
            # Missing/null: a required input is always V001 (spec §4 V001).
            if (!optional) {
              add("V001", iid)
              next
            }
            absent <- TRUE
          } else if (identical(raw, character())) {
            # Empty selection: V001 only when min_selected >= 1.
            absent <- optional
            if (!optional && (spec$min_selected %||% 1L) >= 1L) {
              add("V001", iid)
              next
            }
          } else {
            absent <- FALSE
      }
    } else {
      absent <- is.null(raw) || identical(raw, "")
      if (absent && !optional) {
        add("V001", iid)
        next
      }
    }

    if (absent) {
      for (n in names) {
        macros[[n]] <- ""
      }
      if (identical(kind, "multichoice") && !is.null(spec$count_macro)) {
        macros[[names[length(names)]]] <- "0"
      }
      next
    }

    res <- .sashiny_render_one(iid, spec, raw, today, choices_override)
    if (!is.null(res$err)) {
      add(res$err$code, res$err$path, res$err$message)
      next
    }
    rendered <- res$rendered
    for (j in seq_along(names)) {
      if (nchar(rendered[[j]], type = "bytes") > .sashiny_max_macro_bytes) {
        add("V013", iid)
        break
      }
      macros[[names[[j]]]] <- rendered[[j]]
    }
  }

  list(macros = macros, issues = issues)
}

#' Render a single validated value.
#' Returns a list with `err` (a `sashiny_issue` or NULL) and `rendered`
#' (a character vector).
#' @noRd
.sashiny_render_one <- function(iid, spec, raw, today, override) {
  kind <- spec$type
  err <- function(code) list(err = sashiny_issue(code, iid), rendered = character())

  if (identical(kind, "numeric")) {
    if (is.logical(raw) || !is.numeric(raw)) {
      return(err("V002"))
    }
    if (!is.finite(raw)) {
      return(err("V003"))
    }
    if (isTRUE(spec$integer) && raw != floor(raw)) {
      return(err("V012"))
    }
    if ((!is.null(spec$min) && raw < spec$min) || (!is.null(spec$max) && raw > spec$max)) {
      return(err("V003"))
    }
    return(list(err = NULL, rendered = .sashiny_render_number(raw)))
  }

  if (identical(kind, "text")) {
    if (!is.character(raw)) {
      return(err("V002"))
    }
    if (grepl(.sashiny_control, raw, perl = TRUE)) {
      return(err("V007"))
    }
    if (nchar(raw) > (spec$max_length %||% 256L)) {
      return(err("V006"))
    }
    if (!is.null(spec$pattern) && !grepl(paste0("^(?:", spec$pattern, ")$"), raw, perl = TRUE)) {
      return(err("V005"))
    }
    return(list(err = NULL, rendered = .sashiny_render_text(raw, spec$render %||% "raw")))
  }

  if (identical(kind, "choice")) {
    if (!is.character(raw)) {
      return(err("V002"))
    }
    if (grepl(.sashiny_control, raw, perl = TRUE)) {
      return(err("V007"))
    }
    allowed <- if ("choices" %in% names(spec)) .sashiny_choice_values(spec) else override[[iid]]
    if (!is.null(allowed) && !(raw %in% allowed)) {
      return(err("V004"))
    }
    return(list(err = NULL, rendered = .sashiny_render_text(raw, spec$render %||% "raw")))
  }

  if (identical(kind, "multichoice")) {
    if (!is.character(raw)) {
      return(err("V002"))
    }
    if (any(grepl(.sashiny_control, raw, perl = TRUE))) {
      return(err("V007"))
    }
    allowed <- if ("choices" %in% names(spec)) .sashiny_choice_values(spec) else override[[iid]]
    if (!is.null(allowed) && any(!(raw %in% allowed))) {
      return(err("V004"))
    }
    lo <- spec$min_selected %||% 1L
    hi <- spec$max_selected %||% length(raw)
    if (length(unique(raw)) != length(raw) || !(lo <= length(raw) && length(raw) <= hi)) {
      return(err("V008"))
    }
    ordered <- if (!is.null(allowed)) allowed[allowed %in% raw] else raw
    mode <- spec$render %||% "quoted"
    parts <- if (identical(mode, "bare")) ordered else vapply(ordered, .sashiny_render_text, character(1), mode = mode)
    sep <- if (identical(spec$separator %||% "space", "comma")) ", " else " "
    out <- paste(parts, collapse = sep)
    if (!is.null(spec$count_macro)) {
      out <- c(out, as.character(length(parts)))
    }
    return(list(err = NULL, rendered = out))
  }

  if (kind %in% c("date", "daterange")) {
    items <- if (identical(kind, "date")) list(raw) else raw
    if (identical(kind, "daterange") && (!is.character(raw) || length(raw) != 2L)) {
      return(err("V002"))
    }
    dates <- list()
    for (it in items) {
      if (!is.character(it)) {
        return(err("V002"))
      }
      dt <- tryCatch(
        {
          if (!grepl("^\\d{4}-\\d{2}-\\d{2}$", it)) stop("bad date")
          .sashiny_resolve_date(it, today)
        },
        error = function(e) NULL
      )
      if (is.null(dt)) {
        return(err("V009"))
      }
      if ((!is.null(spec$min) && dt < .sashiny_resolve_date(spec$min, today)) ||
        (!is.null(spec$max) && dt > .sashiny_resolve_date(spec$max, today))) {
        return(err("V009"))
      }
      dates[[length(dates) + 1L]] <- dt
    }
    if (identical(kind, "daterange") && dates[[1]] > dates[[2]]) {
      return(err("V010"))
    }
    mode <- spec$render %||% "literal"
    return(list(err = NULL, rendered = vapply(dates, .sashiny_render_date, character(1), mode = mode)))
  }

  stop("unknown input type: ", kind)
}
