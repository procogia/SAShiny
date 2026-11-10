# Generated SAS wrapper for SAShiny.
#
# Implements spec/CONTRACT.md section 6: the reset submission and the
# byte-exact main wrapper. The wrapper embeds the user's program text verbatim
# and injects macro values only through single-quoted `call symputx` literals
# followed by `%superq` (spec section 6.3).

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
    for (name in names(macros)) {
      out <- c(out, paste0("%let ", name, " = %superq(", name, ");"))
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
    args <- paste0(names(macros), "=&", names(macros), collapse = ", ")
    tail <- c(tail, paste0("%", run$macro, "(", args, ");"))
  }
  tail <- c(tail, "%put NOTE: SASHINY-END-PROGRAM;")
  for (o in ods) {
    tail <- c(tail, paste0("ods ", o$fmt, "(id=", o$oid, ") close;"))
  }
  tail <- c(tail, paste0("%put NOTE: SASHINY-END run=", run_id, " syscc=&syscc;"))
  paste0(body, paste(tail, collapse = "\n"), "\n")
}
