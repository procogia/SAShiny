# Generated SAS wrapper for SAShiny.
#
# Implements spec/CONTRACT.md section 6: the reset submission and the
# byte-exact main wrapper. The wrapper embeds the user's program text verbatim
# and injects macro values only through single-quoted `call symputx` literals
# followed by `%superq`, and (`entry: macro`) call arguments with `%nrstr`
# masking where needed (spec section 6.3).

#' Generate the reset submission (spec section 6.2)
#'
#' @param data The parsed contract data (a list).
#' @return A character string of the reset SAS code.
#' @export
sas_reset_code <- function(data) {
  lines <- c(
    "/* SAShiny 1 reset */",
    "proc datasets library=work kill nolist nowarn;",
    "quit;"
  )
  names <- .sashiny_all_macro_names(data)
  if (length(names) > 0L) {
    lines <- c(lines, paste0("%symdel ", paste(names, collapse = " "), " / nowarn;"))
  }
  paste0(paste(lines, collapse = "\n"), "\n")
}

#' Generate the main wrapper submission (spec section 6.3)
#'
#' @param data The parsed contract data (a list).
#' @param macros A named character vector of rendered macro values in spec
#'   section 5.7 order.
#' @param program_bytes Raw bytes of the SAS program file.
#' @param run_id The run identifier embedded in the sentinel lines.
#' @return A character string of the complete wrapper text.
#' @export
sas_wrapper_code <- function(data, macros, program_bytes, run_id = "fixture") {
  # Strip a leading UTF-8 BOM at the byte level, so the result does not depend
  # on the session locale (spec section 6.3).
  bom <- as.raw(c(0xef, 0xbb, 0xbf))
  if (length(program_bytes) >= 3L && identical(program_bytes[1:3], bom)) {
    program_bytes <- program_bytes[-(1:3)]
  }
  text <- rawToChar(program_bytes)
  # The program is decoded as UTF-8 (spec section 6.3), whatever the locale.
  Encoding(text) <- "UTF-8"
  text <- gsub("\r\n", "\n", text, fixed = TRUE)
  text <- gsub("\r", "\n", text, fixed = TRUE)
  if (!endsWith(text, "\n")) {
    text <- paste0(text, "\n")
  }

  out <- c(
    "/* SAShiny 1 wrapper: generated, do not edit */",
    paste0("%put NOTE: SASHINY-BEGIN run=", run_id, ";"),
    "%let syscc = 0;"
  )
  if (length(macros) > 0L) {
    out <- c(out, "data _null_;")
    for (name in names(macros)) {
      value <- gsub("'", "''", macros[[name]], fixed = TRUE)
      out <- c(out, paste0("  call symputx('", name, "', '", value, "', 'G');"))
    }
    out <- c(out, "run;")
    needs_superq <- .sashiny_superq_macros(data)
    for (name in names(macros)) {
      if (name %in% needs_superq) {
        out <- c(out, paste0("%let ", name, " = %superq(", name, ");"))
      }
    }
  }

  ods <- list()
  for (oid in names(data$outputs)) {
    spec <- data$outputs[[oid]]
    if (identical(spec$type, "download") && spec$format %in% c("rtf", "pdf")) {
      ods[[length(ods) + 1L]] <- list(oid = oid, fmt = spec$format)
    }
  }
  for (o in ods) {
    out <- c(out, paste0(
      "ods ", o$fmt, "(id=", o$oid, ') file="%sysfunc(pathname(work))/sashiny_',
      o$oid, ".", o$fmt, '";'
    ))
  }
  out <- c(out, "%put NOTE: SASHINY-BEGIN-PROGRAM;")
  body <- paste0(paste(out, collapse = "\n"), "\n", text)

  tail <- character()
  run <- data$run %||% list()
  if (identical(run$entry, "macro")) {
    # With no macro variables the call is `%<MACRO>();` (spec section 6.3).
    args <- if (length(macros) == 0L) {
      ""
    } else {
      args_each <- vapply(names(macros), function(n) {
        paste0(n, "=", .sashiny_macro_arg(macros[[n]]))
      }, character(1), USE.NAMES = FALSE)
      paste(args_each, collapse = ", ")
    }
    tail <- c(tail, paste0("%", run$macro, "(", args, ");"))
  }
  tail <- c(tail, "%put NOTE: SASHINY-END-PROGRAM;")
  for (o in ods) {
    tail <- c(tail, paste0("ods ", o$fmt, "(id=", o$oid, ") close;"))
  }
  tail <- c(tail, paste0("%put NOTE: SASHINY-END run=", run_id, " syscc=&syscc;"))
  paste0(body, paste(tail, collapse = "\n"), "\n")
}

# Macro-quote one character outside a string literal (spec section 6.3).
.sashiny_mask <- function(c) {
  if (c == "%") {
    "%nrstr(%%)"
  } else if (c %in% c("'", '"', "(", ")")) {
    paste0("%nrstr(%", c, ")")
  } else {
    paste0("%nrstr(", c, ")")
  }
}

# Write a rendered value as a macro call argument (spec section 6.3).
#
# Only the characters that would split the call or trigger macro execution are
# wrapped in `%nrstr`: outside string literals `,`, `;`, `&`, `%` and unmatched
# quotes or parentheses; inside double-quoted literals `&` and `%`. Everything
# else, including whole single-quoted literals, is written as is, so SAS reads
# the value as ordinary program text (a macro-quoted value breaks `WHERE`
# clauses and names such as `l&level`, see section 9).
.sashiny_macro_arg <- function(value) {
  ch <- strsplit(enc2utf8(value), "", fixed = TRUE)[[1]]
  n <- length(ch)
  out <- character()
  parens <- integer()
  i <- 1L
  while (i <= n) {
    c <- ch[[i]]
    if (c == "'" || c == '"') {
      j <- i + 1L
      end <- NA_integer_
      while (j <= n) {
        if (ch[[j]] == c) {
          if (j < n && ch[[j + 1L]] == c) {
            j <- j + 2L
            next
          }
          end <- j
          break
        }
        j <- j + 1L
      }
      if (!is.na(end)) {
        seg <- paste(ch[i:end], collapse = "")
        if (c == '"') {
          seg <- gsub("%", .sashiny_mask("%"), seg, fixed = TRUE)
          seg <- gsub("&", .sashiny_mask("&"), seg, fixed = TRUE)
        }
        out <- c(out, seg)
        i <- end + 1L
        next
      }
    }
    if (c == "(" || c == ")") {
      parens <- c(parens, length(out) + 1L)
    }
    out <- c(out, if (c %in% c(",", ";", "&", "%", "'", '"')) .sashiny_mask(c) else c)
    i <- i + 1L
  }
  stack <- integer()
  unmatched <- integer()
  for (idx in parens) {
    if (out[[idx]] == "(") {
      stack <- c(stack, idx)
    } else if (length(stack) > 0L) {
      stack <- stack[-length(stack)]
    } else {
      unmatched <- c(unmatched, idx)
    }
  }
  for (idx in c(unmatched, stack)) {
    out[[idx]] <- .sashiny_mask(out[[idx]])
  }
  paste(out, collapse = "")
}
