# Extracted from test-wrapper.R:41

# test -------------------------------------------------------------------------
fix <- .sashiny_fixtures()
wrapper_dir <- file.path(fix, "wrapper")
dirs <- list.dirs(wrapper_dir, recursive = FALSE)
for (d in dirs) {
    contract <- sas_contract(file.path(d, "contract.sashiny.yml"))
    case <- jsonlite::fromJSON(file.path(d, "case.json"), simplifyVector = FALSE)
    today <- as.Date(case$today)
    issues <- sas_validate(contract, today)
    expect_true(length(issues) == 0L, info = basename(d))

    res <- sas_render_values(contract$data, case$values, today, uploads = case$uploads)
    expect_true(length(res$issues) == 0L, info = basename(d))

    reset_enabled <- (contract$data$run %||% list())$reset_work %||% TRUE
    reset_file <- file.path(d, "expected_reset.sas")
    expect_identical(file.exists(reset_file), reset_enabled, info = basename(d))
    if (reset_enabled && file.exists(reset_file)) {
          want_reset <- readChar(reset_file, file.info(reset_file)$size)
          # Normalise CRLF (git autocrlf on Windows) to LF, as the spec requires.
          want_reset <- gsub("\r\n", "\n", want_reset, fixed = TRUE)
          expect_identical(
            sas_reset_code(contract$data),
            want_reset,
            info = basename(d)
          )
        }

        program <- readBin(file.path(d, contract$data$program), "raw",
                           n = file.info(file.path(d, contract$data$program))$size)
        got <- sas_wrapper_code(contract$data, res$macros, program)
        want <- readChar(file.path(d, "expected_main.sas"),
                         file.info(file.path(d, "expected_main.sas"))$size)
        # Normalise CRLF (git autocrlf on Windows) to LF, as the spec requires.
        want <- gsub("\r\n", "\n", want, fixed = TRUE)
        expect_identical(got, want, info = basename(d))
  }
