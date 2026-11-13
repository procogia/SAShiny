# Result collection helpers (spec/CONTRACT.md section 8).
#
# Pure functions shared by the engines: log splitting and scoping, plot
# extraction from ODS HTML, the SAS code used to collect tables and choices,
# table value assembly, client-side download files and the recording key.
# Every function here has a Python twin in `sashiny.collect` and the two are
# checked against the same fixtures (spec/fixtures/collect).

.sashiny_csv_max_rows <- 1000000L
.sashiny_xpt_v5_max_name <- 8L
.sashiny_begin_program <- "NOTE: SASHINY-BEGIN-PROGRAM"
.sashiny_end_program <- "NOTE: SASHINY-END-PROGRAM"

.sashiny_download_mime <- c(
  csv = "text/csv",
  xlsx = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  xpt = "application/x-sas-xport",
  sas7bdat = "application/x-sas-data",
  rtf = "application/rtf",
  pdf = "application/pdf"
)

# ---------------------------------------------------------------- log

#' Split a SAS log into lines (section 8.2, log)
#'
#' Line breaks are CRLF, CR or LF. A trailing line break does not produce an
#' empty final line. Trailing whitespace is removed from every line.
#' @param log The raw log text.
#' @return A character vector of lines.
#' @noRd
.sashiny_split_log <- function(log) {
  if (is.null(log) || !nzchar(log)) {
    return(character(0))
  }
  lines <- strsplit(log, "\r\n|\r|\n", perl = TRUE)[[1]]
  # strsplit drops one trailing empty piece already; a log ending in a break
  # therefore has no empty final line, matching the spec.
  sub("[[:space:]]+$", "", lines, perl = TRUE)
}

#' Classify one log line (section 8.2, log).
#' @noRd
.sashiny_log_level <- function(line) {
  if (startsWith(line, "ERROR")) {
    "error"
  } else if (startsWith(line, "WARNING")) {
    "warning"
  } else if (startsWith(line, "NOTE")) {
    "note"
  } else {
    "text"
  }
}

#' Classified lines of a log output (section 8.2, log)
#'
#' @param log The main-submission log.
#' @param scope `"program"` (between the program sentinels) or `"full"`.
#' @return A list of `list(level, text)`.
#' @noRd
.sashiny_scope_log <- function(log, scope = "program") {
  lines <- .sashiny_split_log(log)
  if (identical(scope, "program")) {
    begin <- match(.sashiny_begin_program, lines)
    if (is.na(begin)) {
      return(list())
    }
    rest <- lines[-seq_len(begin)]
    end <- match(.sashiny_end_program, rest)
    lines <- if (is.na(end)) rest else rest[seq_len(end - 1L)]
  }
  lapply(lines, function(line) list(level = .sashiny_log_level(line), text = line))
}

# ---------------------------------------------------------------- plots

#' Extract ODS graphs embedded in an HTML document (section 8.2, plot)
#'
#' @param html The ODS HTML document.
#' @param select 1-based position of one graph, or `NULL` for all.
#' @return A list of `list(mime, data)` with base64 `data`.
#' @noRd
.sashiny_extract_plots <- function(html, select = NULL) {
  html <- html %||% ""
  img_re <- paste0(
    "(?i)<img\\b[^>]*?\\bsrc\\s*=\\s*[\"']",
    "data:(image/[A-Za-z0-9.+-]+);base64,([^\"']+)[\"']"
  )
  svg_re <- "(?is)<svg\\b.*?</svg>"
  found <- list()
  pos <- integer(0)
  m <- gregexpr(img_re, html, perl = TRUE)[[1]]
  if (m[1] != -1L) {
    starts <- attr(m, "capture.start")
    lens <- attr(m, "capture.length")
    for (i in seq_along(m)) {
      mime <- tolower(substr(html, starts[i, 1], starts[i, 1] + lens[i, 1] - 1L))
      data <- substr(html, starts[i, 2], starts[i, 2] + lens[i, 2] - 1L)
      found[[length(found) + 1L]] <- list(mime = mime, data = data)
      pos <- c(pos, m[i])
    }
  }
  m <- gregexpr(svg_re, html, perl = TRUE)[[1]]
  if (m[1] != -1L) {
    svgs <- regmatches(html, list(m))[[1]]
    for (i in seq_along(svgs)) {
      data <- .sashiny_b64enc(charToRaw(enc2utf8(svgs[[i]])))
      found[[length(found) + 1L]] <- list(mime = "image/svg+xml", data = data)
      pos <- c(pos, m[i])
    }
  }
  plots <- found[order(pos)]
  if (is.null(select)) {
    return(plots)
  }
  if (select < 1) {
    stop(sprintf("select=%d but graph positions are 1-based", select), call. = FALSE)
  }
  if (select > length(plots)) {
    stop(sprintf("select=%d but the run produced %d graph(s)", select, length(plots)),
      call. = FALSE
    )
  }
  plots[select]
}

# ---------------------------------------------------------------- SAS code

#' Split `lib.member` into upper-cased parts.
#' @noRd
.sashiny_split_member <- function(ref) {
  parts <- strsplit(ref, ".", fixed = TRUE)[[1]]
  list(lib = toupper(parts[[1]]), mem = toupper(paste(parts[-1], collapse = ".")))
}

#' SAS code reading column metadata and the row count (section 8.2, table step 1).
#' @noRd
.sashiny_table_meta_code <- function(lib, mem) {
  where <- sprintf('where libname = "%s" and memname = "%s"', lib, mem)
  paste0(paste(c(
    "proc sql noprint;",
    "  create table work._sx_cols as",
    "    select varnum, name, type, format, label",
    "    from dictionary.columns",
    paste0("    ", where),
    "    order by varnum;",
    "  create table work._sx_nobs as",
    "    select nlobs from dictionary.tables",
    paste0("    ", where, ";"),
    "quit;"
  ), collapse = "\n"), "\n")
}

#' SAS code rendering columns as displayed strings (section 8.2, table step 4).
#' @noRd
.sashiny_formatted_table_code <- function(lib, mem, columns, max_rows) {
  k <- length(columns)
  lines <- c(
    "data work._sx_fmt;",
    sprintf(
      "  set %s.%s(obs=%d keep=%s);",
      lib, mem, as.integer(max_rows), paste(columns, collapse = " ")
    ),
    sprintf("  length _sx_c1-_sx_c%d $512;", k),
    sprintf("  _sx_c%d = strip(vvalue(%s));", seq_len(k), columns),
    sprintf("  keep _sx_c1-_sx_c%d;", k),
    "run;"
  )
  paste0(paste(lines, collapse = "\n"), "\n")
}

#' SAS code for a `choices_from` query (section 6.4).
#' @noRd
.sashiny_choices_code <- function(source) {
  value <- source$value_column
  label <- source$label_column
  cols <- if (is.null(label)) value else paste0(value, ", ", label)
  lines <- c(
    sprintf("proc sql outobs=%d noprint;", as.integer(source$max_choices %||% 1000L)),
    "  create table work._sx_choices as",
    paste0("  select distinct ", cols),
    paste0("  from ", source$dataset),
    sprintf("  where not missing(%s)", value),
    sprintf("  order by %s;", value),
    "quit;"
  )
  paste0(paste(lines, collapse = "\n"), "\n")
}

# ---------------------------------------------------------------- tables

#' Normalise one cell to its JSON form (section 8.1).
#' @noRd
.sashiny_clean_cell <- function(value, numeric) {
  if (is.null(value) || length(value) == 0L) {
    return(NULL)
  }
  value <- value[[1]]
  if (length(value) > 1L) {
    value <- value[[1]]
  }
  if (numeric) {
    number <- suppressWarnings(as.numeric(value))
    if (is.na(number)) {
      return(NULL)
    }
    return(number)
  }
  if (is.na(value)) {
    return("")
  }
  sub("[[:space:]]+$", "", as.character(value), perl = TRUE)
}

#' Assemble a table output value (section 8.1)
#'
#' @param meta Selected column metadata: a list of `list(name, type, label, format)`.
#' @param rows A list of rows, each a list of cell values in column order.
#' @param total_rows Logical observation count, or `NULL`.
#' @param max_rows The contract's `max_rows`.
#' @param formatted Whether cells are SAS-formatted strings.
#' @noRd
.sashiny_build_table <- function(meta, rows, total_rows, max_rows, formatted) {
  numeric <- vapply(meta, function(m) !formatted && identical(m$type, "numeric"), logical(1))
  out_rows <- lapply(rows, function(row) {
    cells <- lapply(seq_along(meta), function(j) .sashiny_clean_cell(row[[j]], numeric[[j]]))
    if (formatted) {
      cells <- lapply(cells, function(c) if (is.null(c)) "" else trimws(as.character(c)))
    }
    cells
  })
  list(
    columns = lapply(meta, function(m) {
      list(
        name = as.character(m$name),
        type = m$type,
        label = .sashiny_text_or_empty(m$label),
        format = .sashiny_text_or_empty(m$format)
      )
    }),
    rows = out_rows,
    total_rows = total_rows,
    truncated = !is.null(total_rows) && total_rows > max_rows,
    formatted = formatted
  )
}

#' `""` for NULL/NA, otherwise the trimmed text.
#' @noRd
.sashiny_text_or_empty <- function(x) {
  if (is.null(x) || length(x) == 0L || is.na(x[[1]])) "" else trimws(as.character(x[[1]]))
}

#' Pick the contract's `columns` (case-insensitive, contract order).
#' @noRd
.sashiny_select_columns <- function(meta, wanted) {
  if (is.null(wanted) || length(wanted) == 0L) {
    return(meta)
  }
  wanted <- unlist(wanted)
  names_upper <- toupper(vapply(meta, function(m) as.character(m$name), character(1)))
  idx <- match(toupper(wanted), names_upper)
  if (anyNA(idx)) {
    stop("column(s) not found: ", paste(wanted[is.na(idx)], collapse = ", "), call. = FALSE)
  }
  meta[idx]
}

# ---------------------------------------------------------------- downloads

#' Join a remote SAS directory and file name.
#' @noRd
.sashiny_join_remote <- function(directory, name) {
  sep <- if (grepl("\\", directory, fixed = TRUE)) "\\" else "/"
  paste0(sub("[/\\\\]+$", "", directory), sep, name)
}

#' Format one CSV field (RFC 4180 quoting; missing is empty).
#' @noRd
.sashiny_csv_field <- function(value) {
  if (is.null(value)) {
    return("")
  }
  text <- if (is.numeric(value)) .sashiny_format_number(value) else as.character(value)
  if (grepl("[\",\r\n]", text)) {
    text <- paste0("\"", gsub("\"", "\"\"", text, fixed = TRUE), "\"")
  }
  text
}

#' Shortest round-tripping text of a number (integers without decimals).
#' @noRd
.sashiny_format_number <- function(x) {
  if (is.finite(x) && x == round(x) && abs(x) < 2^53) {
    return(format(x, scientific = FALSE, trim = TRUE, nsmall = 0L))
  }
  format(x, digits = 15L, trim = TRUE)
}

#' Serialise a raw table value to CSV bytes (section 8.2, download).
#' @noRd
.sashiny_csv_bytes <- function(table) {
  header <- vapply(table$columns, function(c) .sashiny_csv_field(c$name), character(1))
  lines <- c(
    paste(header, collapse = ","),
    vapply(table$rows, function(row) {
      paste(vapply(row, .sashiny_csv_field, character(1)), collapse = ",")
    }, character(1))
  )
  charToRaw(enc2utf8(paste0(paste(lines, collapse = "\n"), "\n")))
}

#' A table value as a data frame (NULL cells become NA).
#' @noRd
.sashiny_table_df <- function(table) {
  cols <- lapply(seq_along(table$columns), function(j) {
    numeric <- identical(table$columns[[j]]$type, "numeric") && !isTRUE(table$formatted)
    values <- lapply(table$rows, function(row) row[[j]])
    if (numeric) {
      vapply(values, function(v) if (is.null(v)) NA_real_ else as.numeric(v), numeric(1))
    } else {
      vapply(values, function(v) if (is.null(v)) NA_character_ else as.character(v), character(1))
    }
  })
  names(cols) <- vapply(table$columns, function(c) c$name, character(1))
  as.data.frame(cols, stringsAsFactors = FALSE, check.names = FALSE, optional = TRUE)
}

#' Serialise a raw table value to XLSX bytes (needs openxlsx).
#' @noRd
.sashiny_xlsx_bytes <- function(table, sheet) {
  .sashiny_need("openxlsx", "to create xlsx downloads")
  path <- tempfile(fileext = ".xlsx")
  on.exit(unlink(path), add = TRUE)
  openxlsx::write.xlsx(.sashiny_table_df(table), path, sheetName = substr(sheet, 1L, 31L))
  .sashiny_read_bytes(path)
}

#' Serialise a raw table value to SAS transport bytes (needs haven).
#' @noRd
.sashiny_xpt_bytes <- function(table, member) {
  .sashiny_need("haven", "to create xpt downloads")
  names <- vapply(table$columns, function(c) c$name, character(1))
  short <- nchar(member) <= .sashiny_xpt_v5_max_name &&
    all(nchar(names) <= .sashiny_xpt_v5_max_name)
  df <- .sashiny_table_df(table)
  for (j in seq_along(table$columns)) {
    label <- table$columns[[j]]$label
    if (nzchar(label)) attr(df[[j]], "label") <- label
  }
  path <- tempfile(fileext = ".xpt")
  on.exit(unlink(path), add = TRUE)
  haven::write_xpt(df, path, version = if (short) 5L else 8L, name = substr(member, 1L, 32L))
  readBin(path, "raw", n = file.info(path)$size)
}

#' Build a download output value (section 8.1).
#' @noRd
.sashiny_download_value <- function(filename, fmt, data) {
  list(
    filename = paste0(filename, ".", fmt),
    mime = .sashiny_download_mime[[fmt]],
    data = .sashiny_b64enc(data)
  )
}

# ---------------------------------------------------------------- recordings

#' The text whose SHA-256 is the recording key (section 8.3).
#'
#' @param contract_sha256 SHA-256 of the contract YAML bytes.
#' @param macros A named list of rendered macro values, in section 5.7 order.
#' @param uploads A named character vector of upload SHA-256 values, in
#'   contract order.
#' @noRd
.sashiny_recording_key_text <- function(contract_sha256, macros, uploads = character(0)) {
  lines <- c("sashiny-recording-key 1", paste0("contract ", contract_sha256))
  if (length(macros) > 0L) {
    lines <- c(lines, paste0("macro ", names(macros), "=", vapply(macros, as.character, "")))
  }
  if (length(uploads) > 0L) {
    lines <- c(lines, paste0("upload ", names(uploads), " ", unname(uploads)))
  }
  paste0(paste(lines, collapse = "\n"), "\n")
}

#' The recording key (section 8.3).
#' @noRd
.sashiny_recording_key_hash <- function(contract_sha256, macros, uploads = character(0)) {
  text <- .sashiny_recording_key_text(contract_sha256, macros, uploads)
  .sashiny_sha256(charToRaw(enc2utf8(text)))
}
