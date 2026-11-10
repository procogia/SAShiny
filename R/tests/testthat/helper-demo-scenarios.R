# Demo scenarios (examples/demo-scenarios.yml) and the result checker.
#
# Mirrors Python/tests/demo_scenarios.py. The scenarios live in the repo's
# examples/ folder, which is not part of the package, so the tests that use
# them skip when it is absent (as under R CMD check).

.demo_examples <- function() {
  normalizePath(file.path("..", "..", "..", "examples"), mustWork = FALSE)
}

.demo_today <- as.Date("2026-11-11")

# Leading bytes of each download format.
.demo_magic <- list(
  pdf = charToRaw("%PDF-"),
  rtf = charToRaw("{\\rtf"),
  xlsx = as.raw(c(0x50, 0x4b, 0x03, 0x04)),
  xpt = charToRaw("HEADER RECORD*******LIBRARY HEADER RECORD"),
  sas7bdat = c(raw(12), as.raw(c(
    0xc2, 0xea, 0x81, 0x60, 0xb3, 0x14, 0x11, 0xcf, 0xbd, 0x92,
    0x08, 0x00, 0x09, 0xc7, 0x31, 0x8c, 0x18, 0x1f, 0x10, 0x11
  )))
)
.demo_mimes <- c("image/png", "image/svg+xml", "image/jpeg", "image/gif")

skip_if_no_demo_scenarios <- function() {
  if (!file.exists(file.path(.demo_examples(), "demo-scenarios.yml"))) {
    skip("examples/demo-scenarios.yml is not available (not a repo checkout)")
  }
}

# Read every scenario. Sequences stay lists, as in contracts (spec section 1.1).
demo_scenarios <- function() {
  examples <- .demo_examples()
  data <- yaml::read_yaml(file.path(examples, "demo-scenarios.yml"),
    handlers = list(seq = function(x) as.list(x))
  )
  lapply(data$scenarios, function(s) {
    uploads <- s$uploads %||% list()
    bad <- names(uploads)[!vapply(uploads, identical, logical(1), "sample")]
    if (length(bad) > 0L) stop(s$id, ": upload ", bad[[1]], " must be 'sample'")
    list(
      id = s$id, title = s$title,
      contract_path = file.path(examples, s$contract),
      primary = isTRUE(s$primary),
      values = s$values %||% list(),
      upload_ids = names(uploads) %||% character(0),
      uploads = stats::setNames(rep(list(TRUE), length(uploads)), names(uploads)),
      expect = s$expect %||% list()
    )
  })
}

demo_scenario <- function(id) {
  Filter(function(s) identical(s$id, id), demo_scenarios())[[1]]
}

# Differences between a primary scenario and what the untouched UI sends.
demo_default_problems <- function(scenario, contract) {
  problems <- character(0)
  inputs <- contract$data$inputs %||% list()
  for (iid in names(inputs)) {
    spec <- inputs[[iid]]
    if (identical(spec$type, "dataset")) {
      if (!is.null(spec$sample) && !iid %in% scenario$upload_ids) {
        problems <- c(problems, sprintf(
          "%s: the UI ticks 'Use the sample file' but the scenario does not", iid
        ))
      }
      next
    }
    if (!is.null(spec$default) && !identical(scenario$values[[iid]], spec$default)) {
      problems <- c(problems, sprintf(
        "%s: scenario value %s != contract default %s", iid,
        deparse1(scenario$values[[iid]]), deparse1(spec$default)
      ))
    }
  }
  problems
}

.demo_starts_with <- function(data, magic) {
  length(data) >= length(magic) && identical(data[seq_along(magic)], magic)
}

.demo_download_problems <- function(oid, fmt, value, contract) {
  spec <- contract$data$outputs[[oid]]
  expected <- paste0(spec$filename %||% oid, ".", fmt)
  problems <- character(0)
  if (!identical(value$filename, expected)) {
    problems <- sprintf("%s: filename %s != %s", oid, deparse1(value$filename), expected)
  }
  data <- tryCatch(openssl::base64_decode(value$data %||% ""), error = function(e) NULL)
  if (is.null(data) || length(data) == 0L) {
    return(c(problems, sprintf("%s: download is empty or not base64", oid)))
  }
  if (identical(fmt, "csv")) {
    lines <- strsplit(rawToChar(data), "\r?\n")[[1]]
    if (sum(nzchar(lines)) < 2L) problems <- c(problems, sprintf("%s: CSV has no data rows", oid))
  } else if (!.demo_starts_with(data, .demo_magic[[fmt]])) {
    problems <- c(problems, sprintf("%s: not a valid .%s file", oid, fmt))
  }
  problems
}

# Every reason the result is not demo-ready (empty = ready).
demo_check_result <- function(result, contract, scenario) {
  expect <- scenario$expect
  want <- expect$status %||% "success"
  problems <- character(0)
  if (!identical(result$status, want)) {
    problems <- sprintf("status '%s' != '%s'", result$status, want)
  }
  meta <- result$metadata
  if (length(meta$issues) > 0L) {
    msgs <- vapply(meta$issues, function(i) paste(i$code, i$message), "")
    problems <- c(problems, paste("issues:", paste(msgs, collapse = "; ")))
  }
  if (!is.null(meta$engine_error)) problems <- c(problems, paste("engine_error:", meta$engine_error))
  collect_errors <- unlist(meta$collect_errors)
  if (length(collect_errors) > 0L) problems <- c(problems, paste("collect error:", collect_errors))
  for (oid in names(contract$data$outputs)) {
    spec <- contract$data$outputs[[oid]]
    value <- result$outputs[[oid]]
    if (is.null(value)) {
      problems <- c(problems, sprintf("%s: missing from outputs", oid))
      next
    }
    if (is.list(value) && !is.null(names(value)) && !is.null(value$error)) {
      problems <- c(problems, sprintf("%s: %s", oid, value$error))
      next
    }
    problems <- c(problems, switch(spec$type,
      table = {
        minimum <- expect$tables[[oid]]$min_rows %||% 0
        c(
          if (length(value$rows) < minimum) {
            sprintf("%s: %d rows, expected at least %d", oid, length(value$rows), minimum)
          },
          if (length(value$columns) == 0L) sprintf("%s: no columns", oid)
        )
      },
      plot = {
        minimum <- expect$plots[[oid]] %||% 0
        mimes <- vapply(value, function(p) p$mime, "")
        c(
          if (length(value) < minimum) {
            sprintf("%s: %d graphs, expected at least %d", oid, length(value), minimum)
          },
          sprintf("%s: unexpected mime %s", oid, setdiff(mimes, .demo_mimes))
        )
      },
      html = if (!grepl("<html", value, ignore.case = TRUE)) {
        sprintf("%s: not an HTML document", oid)
      },
      log = {
        levels <- vapply(value, function(l) l$level, "")
        texts <- vapply(value, function(l) l$text, "")
        c(
          sprintf("%s: SAS log error: %s", oid, texts[levels == "error"]),
          if (length(value) == 0L) sprintf("%s: program log is empty", oid)
        )
      },
      download = .demo_download_problems(oid, spec$format, value, contract)
    ))
  }
  problems
}

# Row values of every table output, for comparing runs.
demo_tables <- function(result) {
  is_table <- vapply(result$outputs, function(v) is.list(v) && !is.null(v$rows), logical(1))
  lapply(result$outputs[is_table], function(v) v$rows)
}
