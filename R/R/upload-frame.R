# Data frames as dataset inputs (spec/CONTRACT.md sections 6.10 and 7.1).
#
# A data frame supplied through `values` or `sas_run(uploads = )` is written as
# CSV in a canonical form, identical byte for byte to what the Python library
# writes, and then goes through the same conversion as an uploaded file.
# Mirrors `sashiny.upload.frame_csv`.

#' A data frame supplied for a dataset input, waiting to be written as CSV.
#'
#' Wrapping keeps it apart from a Shiny `fileInput` value, which is also a data
#' frame (with `datapath` and `name` columns).
#' @noRd
.sashiny_upload_frame <- function(frame, id) {
  structure(list(frame = frame, id = id), class = "sashiny_upload_frame")
}

#' Write a data frame as a canonical CSV file `<id>.csv` in a new temporary
#' folder and return it as an upload file (spec section 7.1).
#' @noRd
.sashiny_frame_upload <- function(frame, id) {
  bytes <- .sashiny_frame_csv(frame)
  dir <- tempfile("sashiny-frame-")
  dir.create(dir)
  path <- file.path(dir, paste0(id, ".csv"))
  writeBin(bytes, path)
  .sashiny_upload_file(path, basename(path))
}

#' Canonical CSV bytes of a data frame (spec section 7.1).
#'
#' @param frame A data frame (a tibble counts).
#' @return A raw vector: UTF-8 text, LF line endings, no byte order mark.
#' @noRd
.sashiny_frame_csv <- function(frame) {
  if (!is.data.frame(frame)) {
    .sashiny_upload_error("a dataset value must be a data frame")
  }
  if (ncol(frame) == 0L) {
    .sashiny_upload_error("the data frame has no columns")
  }
  columns <- lapply(seq_along(frame), function(i) .sashiny_frame_column(frame[[i]], names(frame)[[i]]))
  lines <- .sashiny_frame_quote(enc2utf8(names(frame)))
  header <- paste(lines, collapse = ",")
  rows <- if (nrow(frame) > 0L) do.call(paste, c(columns, sep = ",")) else character(0)
  text <- paste0(paste(c(header, rows), collapse = "\n"), "\n")
  charToRaw(enc2utf8(text))
}

#' One column as quoted CSV fields (spec section 7.1, rule 5).
#' @noRd
.sashiny_frame_column <- function(x, name) {
  .sashiny_frame_quote(.sashiny_frame_texts(x, name))
}

#' One column as unquoted spec section 7.1 rule 5 texts.
#'
#' Also used for declared character upload columns (spec section 7, step 3).
#' @noRd
.sashiny_frame_texts <- function(x, name) {
  if (is.factor(x)) {
    labels <- levels(x)
    x <- labels[as.integer(x)]
  }
  if (inherits(x, "POSIXct")) {
    .sashiny_frame_datetime(x)
  } else if (inherits(x, "Date")) {
    out <- format(x, "%Y-%m-%d")
    out[is.na(x)] <- ""
    out
  } else if (is.logical(x)) {
    ifelse(is.na(x), "", ifelse(x, "1", "0"))
  } else if (is.integer(x) && !is.factor(x) && is.null(attr(x, "class"))) {
    ifelse(is.na(x), "", formatC(x, format = "d"))
  } else if (is.double(x) && is.null(attr(x, "class"))) {
    if (any(is.infinite(x))) {
      .sashiny_upload_error("column '", name, "' has an infinite value, which CSV cannot hold")
    }
    .sashiny_g17_vec(x)
  } else if (is.character(x)) {
    out <- enc2utf8(x)
    out[is.na(out)] <- ""
    out
  } else {
    .sashiny_upload_error("column '", name, "' has a type that cannot be written as CSV (",
                          paste(class(x), collapse = "/"), ")")
  }
}

#' Doubles as C printf "%.17g", correctly rounded; NA and NaN are empty.
#'
#' R's sprintf() is not correctly rounded on every platform (on Windows about
#' 0.3% of doubles differ in the 17th digit), so the digits are computed
#' exactly. A double is m * 2^e with integer m, so its decimal expansion is
#' finite: m * 2^e for e >= 0, or m * 5^-e / 10^-e. That integer is built in
#' base-1e7 limbs (every product stays under 2^53, so it is exact), vectorised
#' over all values that share an exponent, then rounded to 17 significant
#' digits half to even and laid out as "%g" does. Whole numbers below 2^53
#' need no rounding and are printed directly.
#' @noRd
.sashiny_g17_vec <- function(x) {
  out <- character(length(x))
  ok <- !is.na(x)
  zero <- ok & x == 0
  out[zero] <- ifelse(1 / x[zero] < 0, "-0", "0")
  whole <- ok & !zero & abs(x) < 2^53 & x == trunc(x)
  out[whole] <- formatC(x[whole], format = "f", digits = 0, big.mark = "")
  rest <- which(ok & !zero & !whole)
  if (!length(rest)) {
    return(out)
  }
  v <- x[rest]
  bytes <- matrix(as.integer(writeBin(abs(v), raw(), size = 8L, endian = "little")), nrow = 8L)
  bytes <- bytes[8:1, , drop = FALSE] # big-endian, one column per value
  biased <- bytes[1, ] %% 128L * 16L + bytes[2, ] %/% 16L
  frac <- (bytes[2, ] %% 16L) * 2^48 + colSums(bytes[3:8, , drop = FALSE] * 256^(5:0))
  m <- ifelse(biased == 0L, frac, frac + 2^52)
  e <- ifelse(biased == 0L, -1074L, biased - 1075L)
  digits <- character(length(v))
  point <- integer(length(v))
  for (ex in unique(e)) {
    idx <- which(e == ex)
    limbs <- cbind(m[idx] %% 1e7, (m[idx] %/% 1e7) %% 1e7, m[idx] %/% 1e14)
    limbs <- if (ex >= 0) .sashiny_bigv_mul_pow(limbs, 2, ex) else .sashiny_bigv_mul_pow(limbs, 5, -ex)
    text <- do.call(paste0, lapply(rev(seq_len(ncol(limbs))), function(j) sprintf("%07.0f", limbs[, j])))
    digits[idx] <- sub("^0+", "", text)
    point[idx] <- if (ex >= 0) 0L else -ex
  }
  # value = 0.<digits> * 10^(nchar - point): the leading digit's exponent is
  exponent <- nchar(digits) - point - 1L
  rounded <- .sashiny_round17(digits)
  exponent <- exponent + rounded$carry
  out[rest] <- .sashiny_g_layout(ifelse(v < 0, "-", ""), rounded$digits, exponent, 17L)
  out
}

#' Multiply rows of base-1e7 limbs (one row per number, little-endian columns)
#' by base^k, in steps of 2^20 or 5^9 so that every product is exact.
#' @noRd
.sashiny_bigv_mul_pow <- function(limbs, base, k) {
  step <- if (base == 2) 20L else 9L
  while (k > 0) {
    n <- min(k, step)
    f <- base^n
    carry <- numeric(nrow(limbs))
    for (j in seq_len(ncol(limbs))) {
      p <- limbs[, j] * f + carry
      limbs[, j] <- p %% 1e7
      carry <- (p - limbs[, j]) / 1e7
    }
    while (any(carry > 0)) {
      col <- carry %% 1e7
      limbs <- cbind(limbs, col)
      carry <- (carry - col) / 1e7
    }
    k <- k - n
  }
  limbs
}

#' Round digit strings to 17 significant digits, half to even.
#'
#' The 17 kept digits are handled as a 9-digit and an 8-digit number so the
#' increment is exact.
#' @return `list(digits, carry)`: `carry` is 1 where rounding added a leading
#'   digit (999... became 1000...), else 0.
#' @noRd
.sashiny_round17 <- function(digits) {
  n <- nchar(digits)
  long <- n > 17L
  carry <- integer(length(digits))
  if (!any(long)) {
    return(list(digits = digits, carry = carry))
  }
  d <- digits[long]
  head <- substr(d, 1L, 17L)
  first <- as.integer(substr(d, 18L, 18L))
  tail_nonzero <- grepl("[1-9]", substr(d, 19L, nchar(d)))
  last_odd <- as.integer(substr(head, 17L, 17L)) %% 2L == 1L
  up <- first > 5L | (first == 5L & (tail_nonzero | last_odd))
  hi <- as.numeric(substr(head, 1L, 9L))
  lo <- as.numeric(substr(head, 10L, 17L)) + up
  over <- lo >= 1e8
  lo[over] <- 0
  hi <- hi + over
  grown <- hi >= 1e9 # 99999999999999999 rounded up
  hi[grown] <- 1e8
  digits[long] <- paste0(sprintf("%09.0f", hi), sprintf("%08.0f", lo))
  carry[long] <- as.integer(grown)
  list(digits = digits, carry = carry)
}

#' Lay out significant digits the way C printf "%.<p>g" does (vectorised).
#' @noRd
.sashiny_g_layout <- function(sign, digits, exponent, p) {
  digits <- sub("0+$", "", digits)
  digits[!nzchar(digits)] <- "0"
  n <- nchar(digits)
  sci <- exponent < -4L | exponent >= p
  out <- character(length(digits))
  # Exponent style: d[.ddd]e+XX
  mant <- ifelse(n > 1L, paste0(substr(digits, 1L, 1L), ".", substr(digits, 2L, n)), digits)
  out[sci] <- sprintf("%s%se%s%02d", sign[sci], mant[sci], ifelse(exponent[sci] < 0L, "-", "+"),
                      abs(exponent[sci]))
  # Fixed style, below 1: 0.000ddd
  small <- !sci & exponent < 0L
  out[small] <- paste0(sign[small], "0.", strrep("0", -exponent[small] - 1L), digits[small])
  # Fixed style, 1 or more: ddd[.ddd]
  big <- !sci & exponent >= 0L
  int_len <- exponent + 1L
  pad <- big & n <= int_len
  out[pad] <- paste0(sign[pad], digits[pad], strrep("0", int_len[pad] - n[pad]))
  frac <- big & n > int_len
  out[frac] <- paste0(sign[frac], substr(digits[frac], 1L, int_len[frac]), ".",
                      substr(digits[frac], int_len[frac] + 1L, n[frac]))
  out
}

#' Date-times as YYYY-MM-DDTHH:MM:SS[.ffffff]Z in UTC, rounded to the
#' microsecond, without trailing zeros in the fraction.
#' @noRd
.sashiny_frame_datetime <- function(x) {
  secs <- as.numeric(x)
  out <- character(length(secs))
  ok <- !is.na(secs)
  micros <- round(secs[ok] * 1e6)
  whole <- floor(micros / 1e6)
  frac <- micros - whole * 1e6
  base <- format(as.POSIXct(whole, origin = "1970-01-01", tz = "UTC"), "%Y-%m-%dT%H:%M:%S", tz = "UTC")
  fraction <- ifelse(frac > 0, sub("0+$", "", sprintf(".%06d", as.integer(frac))), "")
  out[ok] <- paste0(base, fraction, "Z")
  out
}

#' Quote CSV fields that contain a comma, a double quote, CR or LF.
#' @noRd
.sashiny_frame_quote <- function(x) {
  needs <- grepl("[,\"\r\n]", x, useBytes = TRUE)
  x[needs] <- paste0("\"", gsub("\"", "\"\"", x[needs], fixed = TRUE), "\"")
  x
}
