# Tests for the runner layer.

test_that("sas_run accepts a contract object", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "minimal", "contract.sashiny.yml"))
  result <- sas_run(contract, .sashiny_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run accepts a contract path", {
  path <- file.path(.sashiny_fixtures(), "contracts", "valid",
                    "minimal", "contract.sashiny.yml")
  result <- sas_run(path, .sashiny_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
})

test_that("sas_run reports invalid values", {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "numeric", "contract.sashiny.yml"))
  result <- sas_run(contract, .sashiny_engine_mock(), list(min_msrp = "bad"),
                    today = .sashiny_today)
  expect_identical(result$status, "error")
})
test_that("the old names and argument order still work, with deprecation warnings", {
  withr::local_options(lifecycle_verbosity = "warning")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "minimal",
    "contract.sashiny.yml"))
  engine <- .sashiny_engine_mock()
  expect_warning(old <- sas_run(contract, list(), engine, today = .sashiny_today),
    class = "lifecycle_warning_deprecated")
  expect_identical(old$status, "success")
  pool <- sas_pool(engine)
  expect_warning(res <- sas_pool_run(pool, contract, list(), today = .sashiny_today),
    class = "lifecycle_warning_deprecated")
  expect_identical(res$status, "success")
  expect_warning(sas_pool_close(pool), class = "lifecycle_warning_deprecated")
  data <- list(sashiny = 1L, program = "p.sas", title = "t", outputs = list(log = list(type = "log")))
  expect_warning(lints <- sashiny_lint(data, "run;"), class = "lifecycle_warning_deprecated")
  expect_identical(lints, sas_lint(data, "run;"))
})

test_that("the new forms do not warn", {
  withr::local_options(lifecycle_verbosity = "warning")
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", "minimal",
    "contract.sashiny.yml"))
  pool <- sas_pool(.sashiny_engine_mock())
  expect_no_warning(sas_run(contract, pool, today = .sashiny_today))
  expect_no_warning(sas_close(pool))
})

.sashiny_valid_contract <- function(name) {
  sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid", name, "contract.sashiny.yml"))
}

test_that("sas_run without values uses the contract defaults (#162)", {
  # Inputs not supplied take their `default` (spec section 6.12).
  for (values in list(NULL, list())) {
    result <- sas_run(.sashiny_valid_contract("numeric"), .sashiny_engine_mock(), values,
      today = .sashiny_today)
    expect_identical(result$status, "success")
    expect_identical(result$metadata$macros$MIN_MSRP, "20000")
    expect_identical(result$metadata$macros$RATIO_VALUE, "0.5")
    expect_identical(result$metadata$macros$BIG, "")
  }
})

test_that("sas_run resolves today defaults against today", {
  result <- sas_run(.sashiny_valid_contract("dates"), .sashiny_engine_mock(), today = .sashiny_today)
  expect_identical(result$status, "success")
  macros <- result$metadata$macros
  expect_identical(macros$CUTOFF, "'11NOV2026'd")
  expect_identical(macros$PERIOD_START, "'01JAN2026'd")
  expect_identical(macros$PERIOD_END, "'30JUN2026'd")
})

test_that("supplied values replace defaults and NULL makes an input absent", {
  result <- sas_run(.sashiny_valid_contract("numeric"), .sashiny_engine_mock(),
    list(min_msrp = 5000), today = .sashiny_today)
  expect_identical(result$metadata$macros$MIN_MSRP, "5000")
  expect_identical(result$metadata$macros$RATIO_VALUE, "0.5")
  absent <- sas_run(.sashiny_valid_contract("numeric"), .sashiny_engine_mock(),
    list(ratio = NULL), today = .sashiny_today)
  expect_identical(absent$status, "error")
  expect_identical(vapply(absent$metadata$issues, function(i) i$code, character(1)), "V001")
  expect_identical(absent$metadata$issues[[1]]$input, "ratio")
})

test_that("sas_run defaults fill multichoice inputs", {
  # `types` has no default, so it is absent unless supplied (spec section 6.12).
  missing <- sas_run(.sashiny_valid_contract("multichoice"), .sashiny_engine_mock(),
    today = .sashiny_today)
  expect_identical(missing$metadata$issues[[1]]$code, "V001")
  expect_identical(missing$metadata$issues[[1]]$input, "types")
  expect_length(missing$metadata$issues, 1L)
  result <- sas_run(.sashiny_valid_contract("multichoice"), .sashiny_engine_mock(),
    list(types = list()), today = .sashiny_today)
  expect_identical(result$status, "success")
  expect_identical(result$metadata$macros$ORIGINS, "'Asia' 'Europe' 'USA'")
  expect_identical(result$metadata$macros$N_ORIGINS, "3")
})
