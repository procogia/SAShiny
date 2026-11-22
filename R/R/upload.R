# Dataset upload conversion (spec/CONTRACT.md section 7).
#
# Reads a user-supplied or sample file into a data frame ready for saspy's
# `df2sd`: column names sanitised, declared columns converted and checked, and
# undeclared all-number CSV columns made numeric. Mirrors `sashiny.upload`.

.sashiny_max_name_bytes <- 32L
.sashiny_default_accept <- c("csv", "xlsx", "xpt", "sas7bdat")

#' Signal an upload error (reported as V014).
#' @noRd
.sashiny_upload_error <- function(...) {
  # `sashiny_upload_error` is the class the engines catch to report V014.
  stop(structure(
    class = c("sashiny_upload_error", "sashiny_error_upload", "sashiny_error", "error", "condition"),
    list(message = paste0(...), call = NULL)
  ))
}

#' A supplied file: where it is and its original name.
#' @noRd
.sashiny_upload_file <- function(path, name = basename(path)) {
  structure(list(path = path, name = name), class = "sashiny_upload_file")
}

#' Turn an `uploads` entry into an upload file, or NULL when not supplied
#'
#' `TRUE` selects the contract's `sample`. A path, a Shiny `fileInput` value
#' (a data frame with `datapath` and `name`) or an upload file selects that
#' file. Any other data frame is written as canonical CSV `<id>.csv`
#' (spec section 7.1).
#' @noRd
.sashiny_resolve_upload <- function(value, spec, base_dir, id = "data") {
  if (is.null(value) || isFALSE(value) || (is.character(value) && !nzchar(value[[1]]))) {
    return(NULL)
  }
  if (isTRUE(value)) {
    if (is.null(spec$sample)) {
      .sashiny_upload_error("no file supplied and the input has no sample")
    }
    path <- file.path(base_dir, spec$sample)
    return(.sashiny_upload_file(path, basename(path)))
  }
  if (inherits(value, "sashiny_upload_file")) {
    return(value)
  }
  # A data frame value (spec sections 6.10 and 7.1): written as canonical CSV.
  if (inherits(value, "sashiny_upload_frame")) {
    return(.sashiny_frame_upload(value$frame, value$id))
  }
  if (is.data.frame(value) && all(c("datapath", "name") %in% names(value))) {
    return(.sashiny_upload_file(value$datapath[[1]], value$name[[1]]))
  }
  if (is.data.frame(value)) {
    return(.sashiny_frame_upload(value, id))
  }
  .sashiny_upload_file(as.character(value[[1]]))
}

#' Resolve every dataset input's upload to a named list of upload files.
#' @noRd
.sashiny_resolve_files <- function(contract, uploads) {
  inputs <- contract$data$inputs %||% list()
  files <- list()
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    if (!identical(spec$type, "dataset")) next
    upload <- .sashiny_resolve_upload(uploads[[iid]], spec, contract$base_dir, iid)
    if (!is.null(upload)) {
      # Check extension, existence and size (section 7 step 1); a bad file is
      # reported as V014 rather than a raw error.
      .sashiny_check_upload(upload, spec)
      files[[iid]] <- upload
    }
  }
  files
}

#' Lower-case extension without the dot.
#' @noRd
.sashiny_extension <- function(name) {
  tolower(tools::file_ext(name))
}

#' Sanitise column names (section 7 step 2)
#'
#' Characters outside `[A-Za-z0-9_]` become `_`; a leading digit gets a `_`
#' prefix; names are truncated to 32 bytes; case-insensitive duplicates get
#' `_2`, `_3`, ... suffixes.
#' @noRd
.sashiny_sanitize_names <- function(names) {
  out <- character(length(names))
  seen <- character(0)
  for (i in seq_along(names)) {
    name <- gsub("[^A-Za-z0-9_]", "_", enc2utf8(as.character(names[[i]])), perl = TRUE)
    if (!nzchar(name)) name <- "_"
    if (grepl("^[0-9]", name)) name <- paste0("_", name)
    name <- substr(name, 1L, .sashiny_max_name_bytes)
    candidate <- name
    n <- 1L
    while (toupper(candidate) %in% seen) {
      n <- n + 1L
      suffix <- paste0("_", n)
      candidate <- paste0(substr(name, 1L, .sashiny_max_name_bytes - nchar(suffix)), suffix)
    }
    seen <- c(seen, toupper(candidate))
    out[[i]] <- candidate
  }
  out
}

#' Read a file; returns `list(df, all_text)` where `all_text` marks CSV input.
#' @noRd
.sashiny_read_file <- function(upload) {
  ext <- .sashiny_extension(upload$name)
  if (identical(ext, "csv")) {
    df <- utils::read.csv(upload$path,
      colClasses = "character", na.strings = character(0),
      check.names = FALSE, encoding = "UTF-8", fileEncoding = "UTF-8"
    )
    return(list(df = df, all_text = TRUE))
  }
  if (identical(ext, "xlsx")) {
    .sashiny_need("openxlsx", "to read xlsx uploads")
      # na.strings = character(0) preserves literal "NA"/"nan"/"None" text and
      # leading-zero strings (spec section 7 step 3: only empty/whitespace is missing).
      # Without it openxlsx coerces literal "NA" to a missing value before the
      # declared-column conversion can distinguish it from a blank cell.
    # Blank rows are kept and date-formatted cells become date-times, as
    # pandas/openpyxl read them (spec section 7 step 1): openxlsx skips blank
    # rows and detects only some date formats, so serials are converted here.
    df <- openxlsx::read.xlsx(upload$path, sheet = 1L, detectDates = FALSE, check.names = FALSE,
        sep.names = " ", na.strings = character(0), skipEmptyRows = FALSE
    )
    return(list(df = .sashiny_xlsx_fix(df, upload$path), all_text = FALSE))
  }
  if (ext %in% c("xpt", "sas7bdat")) {
    .sashiny_need("haven", "to read SAS data uploads")
    df <- if (identical(ext, "xpt")) haven::read_xpt(upload$path) else haven::read_sas(upload$path)
    df <- as.data.frame(haven::zap_labels(haven::zap_formats(df)))
    return(list(df = df, all_text = FALSE))
  }
  .sashiny_upload_error("unsupported file type .", ext)
}

#' Whether an Excel number format is a date or time format.
#'
#' The rule openpyxl (and so pandas) uses: a built-in date format id, or a
#' format code that, without quoted text, escaped characters and `[...]`
#' sections, contains one of `d m y h s`.
#' @noRd
.sashiny_xlsx_is_date_format <- function(num_fmt) {
  if (is.null(num_fmt)) {
    return(FALSE)
  }
  id <- suppressWarnings(as.integer(num_fmt$numFmtId %||% NA))
  if (!is.na(id) && id %in% c(14:22, 45:47)) {
    return(TRUE)
  }
  code <- num_fmt$formatCode %||% ""
  if (!nzchar(code) || identical(tolower(code), "general")) {
    return(FALSE)
  }
  code <- gsub("\"[^\"]*\"|\\\\.|\\[[^]]*\\]", "", code, perl = TRUE)
  grepl("[dmyhsDMYHS]", code)
}

#' Align an openxlsx read with pandas/openpyxl (spec section 7 step 1).
#'
#' Columns whose non-empty data cells all carry a date format become UTC
#' date-times from their Excel serials (1900 or 1904 date system). Text cells
#' that openxlsx misreads from inline strings with `xml:space="preserve"`
#' lose that markup prefix.
#' @param df The data frame from `openxlsx::read.xlsx(detectDates = FALSE)`.
#' @param path The xlsx file.
#' @noRd
.sashiny_xlsx_fix <- function(df, path) {
  for (j in seq_along(df)) {
    if (is.character(df[[j]])) {
      df[[j]] <- sub("^xml:space=\"preserve\">", "", df[[j]])
    }
  }
  if (nrow(df) == 0L) {
    return(df)
  }
  wb <- openxlsx::loadWorkbook(path)
  sheet <- wb$sheet_names[[1L]]
  dated <- matrix(FALSE, nrow = nrow(df) + 1L, ncol = ncol(df))
  for (so in wb$styleObjects) {
    if (!identical(so$sheet, sheet) || !.sashiny_xlsx_is_date_format(so$style$numFmt)) next
    keep <- so$rows <= nrow(dated) & so$cols <= ncol(dated)
    dated[cbind(so$rows[keep], so$cols[keep])] <- TRUE
  }
  origin <- if (identical(openxlsx::getDateOrigin(path), "1904-01-01")) 24107 else 25569
  for (j in seq_along(df)) {
    x <- df[[j]]
    present <- !is.na(x)
    if (!is.numeric(x) || !any(present) || !all(dated[which(present) + 1L, j])) next
    # As openpyxl's from_excel(): whole days plus the day fraction rounded to
    # the millisecond (half to even in both languages).
    day <- floor(x)
    ms <- round((x - day) * 86400000)
    df[[j]] <- as.POSIXct((day - origin) * 86400 + ms / 1000, origin = "1970-01-01", tz = "UTC")
  }
  df
}

#' Check extension, existence and size (section 7 step 1).
#' @noRd
.sashiny_check_upload <- function(upload, spec) {
  accept <- unlist(spec$accept %||% .sashiny_default_accept)
  ext <- .sashiny_extension(upload$name)
  if (!(ext %in% accept)) {
    .sashiny_upload_error(
      ".", ext, " is not accepted (accepted: ", paste(accept, collapse = ", "), ")"
    )
  }
  if (!utils::file_test("-f", upload$path)) {
    .sashiny_upload_error("file not found: ", upload$name)
  }
  limit <- spec$max_size_mb %||% 50
  size_mb <- file.info(upload$path)$size / (1024 * 1024)
  if (size_mb > limit) {
    .sashiny_upload_error(sprintf("%s is %.1f MB (limit %s MB)", upload$name, size_mb, limit))
  }
}

#' Parse decimal number text (R's hexadecimal literals are not numbers here).
#' @noRd
.sashiny_as_number <- function(text) {
  out <- suppressWarnings(as.numeric(text))
  out[grepl("^[+-]?0[xX]", text)] <- NA_real_
  out
}

#' Convert a declared numeric column.
#' @noRd
.sashiny_upload_numeric <- function(x, name, all_text) {
  if (is.numeric(x)) {
    return(as.numeric(x))
  }
  text <- trimws(as.character(x), whitespace = "[ \t\r\n\f\v]")
  blank <- is.na(x) | !nzchar(text)
  converted <- .sashiny_as_number(ifelse(blank, NA, text))
  if (any(is.na(converted) & !blank)) {
    .sashiny_upload_error("column ", name, " has values that are not numbers")
  }
  converted
}

#' Convert a declared date column to `Date`.
#' @noRd
.sashiny_upload_date <- function(x, name) {
  if (inherits(x, "Date")) {
    return(x)
  }
  if (inherits(x, "POSIXt")) {
    return(as.Date(x, tz = "UTC"))
  }
  text <- trimws(as.character(x), whitespace = "[ \t\r\n\f\v]")
  # Only native missing and empty/whitespace are "missing" (spec section 7 step 3);
  # any other non-ISO text (including the literal "NA", "nan", "NaT", "None")
  # is unparseable and reported as V014.
  blank <- is.na(x) | !nzchar(text)
  ok <- grepl("^[0-9]{4}-[0-9]{2}-[0-9]{2}$", text)
  parsed <- as.Date(ifelse(blank | !ok, NA, text), format = "%Y-%m-%d")
  if (any(is.na(parsed) & !blank)) {
    .sashiny_upload_error("column ", name, " has values that are not YYYY-MM-DD dates")
  }
  parsed
}

#' Read and convert an upload per section 7
#'
#' @param upload An upload file from `.sashiny_resolve_upload()`.
#' @param spec The contract's dataset input spec.
#' @return `list(df, datetimes)`: the data frame and a named list mapping date
#'   columns to `"date"` for `df2sd`.
#' @noRd
.sashiny_read_upload <- function(upload, spec) {
  .sashiny_check_upload(upload, spec)
  read <- tryCatch(.sashiny_read_file(upload),
    sashiny_upload_error = function(e) stop(e),
    error = function(e) {
      .sashiny_upload_error("could not read ", upload$name, ": ", conditionMessage(e))
    }
  )
  df <- read$df
  names(df) <- .sashiny_sanitize_names(names(df))
  by_upper <- stats::setNames(names(df), toupper(names(df)))
  datetimes <- list()
  declared <- character(0)
  for (col in spec$columns %||% list()) {
    name <- by_upper[toupper(col$name)]
    if (is.na(name)) {
      .sashiny_upload_error(upload$name, " has no column ", col$name)
    }
    name <- unname(name)
    declared <- c(declared, name)
    if (identical(col$type, "numeric")) {
      df[[name]] <- .sashiny_upload_numeric(df[[name]], name, read$all_text)
    } else if (identical(col$type, "date")) {
      df[[name]] <- .sashiny_upload_date(df[[name]], name)
      datetimes[[name]] <- "date"
    } else {
      # Text stays as it is; other native cells take their spec section 7.1
      # rule 5 text (1/0, %.17g, ISO dates), the same text Python writes.
      x <- df[[name]]
      if (inherits(x, "haven_labelled")) x <- unclass(x)
      if (!inherits(x, c("Date", "POSIXct", "factor"))) attr(x, "class") <- NULL
      df[[name]] <- .sashiny_frame_texts(x, name)
    }
  }
  if (read$all_text) {
    for (name in setdiff(names(df), declared)) {
      text <- trimws(df[[name]], whitespace = "[ \t\r\n\f\v]")
      nonblank <- nzchar(text)
      converted <- .sashiny_as_number(ifelse(nonblank, text, NA))
      if (any(nonblank) && !any(is.na(converted) & nonblank)) {
        df[[name]] <- converted
      }
    }
  }
  list(df = df, datetimes = datetimes)
}
