# Conformance tests for value validation and rendering (issue #3).
#
# Reads spec/fixtures/values and asserts exact macro name/value/order for
# "ok" cases and the exact {code, input} set for "invalid" cases.

test_that("value fixtures render correctly", {
  fix <- .sashiny_fixtures()
  values_dir <- file.path(fix, "values")
  files <- list.files(values_dir, pattern = "\\.json$", full.names = TRUE)
  for (vf in files) {
    spec <- jsonlite::fromJSON(vf, simplifyVector = FALSE)
    contract <- sas_contract(file.path(fix, spec$contract, "contract.sashiny.yml"))
    today <- as.Date(spec$today)
    for (case in spec$cases) {
      res <- sas_render_values(
        contract$data,
        case$values,
        today,
        choices_override = case$choices_from,
        uploads = case$uploads
      )
      exp <- case$expected
      label <- paste0(basename(vf), "/", case$name)
      if (identical(exp$status, "ok")) {
        expect_true(length(res$issues) == 0L, info = label)
              # Compare macro name/value pairs, normalising empty-list name attributes.
              got_pairs <- if (length(res$macros) == 0L) character() else
                paste(names(res$macros), unlist(res$macros), sep = "\r")
              exp_pairs <- if (length(exp$macros) == 0L) character() else
                paste(names(exp$macros), unlist(exp$macros), sep = "\r")
              expect_identical(got_pairs, exp_pairs, info = label)
            } else {
        want <- lapply(exp$errors, function(e) c(e$code, e$input))
        got <- lapply(res$issues, function(i) c(i$code, i$path))
        got_s <- sort(vapply(got, function(g) paste(g, collapse = "\r"), character(1)))
        want_s <- sort(vapply(want, function(w) paste(w, collapse = "\r"), character(1)))
        expect_identical(got_s, want_s, info = label)
      }
    }
  }
})
test_that("a multichoice element must be a single string (issue #60)", {
  data <- list(inputs = list(x = list(type = "multichoice", label = "X", choices = list("A", "B"))))
  res <- sas_render_values(data, list(x = list(c("A", "B"))), .sashiny_today)
  expect_identical(vapply(res$issues, function(i) i$code, ""), "V002")
  ok <- sas_render_values(data, list(x = list("A", "B")), .sashiny_today)
  expect_length(ok$issues, 0L)
  range <- list(inputs = list(d = list(type = "daterange", label = "D")))
  bad <- sas_render_values(range, list(d = list(c("2026-01-01", "2026-01-02"), "2026-01-03")),
    .sashiny_today
  )
  expect_identical(vapply(bad$issues, function(i) i$code, ""), "V002")
})

test_that("sas_json_values keeps an escaped U+0000 a V007 error (issue #102)", {
  data <- list(inputs = list(
    company = list(type = "text", label = "Company"),
    pick = list(type = "choice", label = "Pick", choices = list("a"), optional = TRUE)
  ))
  values <- sas_json_values('{"company": "a\\u0000b"}')
  expect_identical(nchar(values$company), 3L)
  res <- sas_render_values(data, values, .sashiny_today)
  expect_identical(vapply(res$issues, function(i) i$code, ""), "V007")
  expect_identical(vapply(res$issues, function(i) i$path, ""), "company")
  # An escaped backslash before "u0000" is literal text, not a NUL escape.
  literal <- sas_json_values('{"company": "a\\\\u0000b"}')
  expect_identical(literal$company, "a\\u0000b")
  expect_length(sas_render_values(data, literal, .sashiny_today)$issues, 0L)
  # Raw bytes are accepted; a literal NUL byte is never silently truncated: it
  # is either a JSON parse error or a V007 value.
  expect_identical(sas_json_values(charToRaw('{"company": "x"}'))$company, "x")
  nul <- tryCatch(
    sas_json_values(c(charToRaw('{"company": "a'), as.raw(0L), charToRaw('b"}'))),
    error = function(e) NULL
  )
  if (!is.null(nul)) {
    expect_identical(sas_render_values(data, nul, .sashiny_today)$issues[[1]]$code, "V007")
  }
  expect_identical(sas_json_values("{}"), structure(list(), names = character()))
  expect_error(sas_json_values("[1, 2]"), "JSON object")
  expect_error(sas_json_values(1), "single JSON string")
})
