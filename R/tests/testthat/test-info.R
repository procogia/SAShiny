# Tests for sas_info() (spec section 11).

test_that("sas_info reports the package, spec release and contract version", {
  info <- sas_info()
  expect_s3_class(info, "sashiny_info")
  expect_identical(info$version, as.character(utils::packageVersion("SAShiny")))
  expect_match(info$spec, "^1\\.[0-9]+$")
  expect_identical(info$contract, 1L)
  expect_output(print(info), "^SAShiny [0-9.]+ \\(spec 1\\.[0-9]+, contract sashiny: 1\\)$")
})

test_that("the spec release matches CONTRACT.md", {
  spec <- file.path(.sashiny_fixtures(), "..", "CONTRACT.md")
  skip_if_not(file.exists(spec))
  line <- grep("Spec release:", readLines(spec, encoding = "UTF-8"), value = TRUE)[[1]]
  expect_identical(sub(".*\\*\\*([0-9.]+)\\*\\*.*", "\\1", line), sas_info()$spec)
})
