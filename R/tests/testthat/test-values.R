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