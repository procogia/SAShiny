test_that("package metadata is in place", {
  desc <- utils::packageDescription("SAShiny")
  expect_identical(desc$Package, "SAShiny")
  expect_match(desc$License, "^MIT")
})

test_that(".sashiny_need() checks presence and minimum version", {
  expect_true(SAShiny:::.sashiny_need("utils", "for this test"))
  expect_true(SAShiny:::.sashiny_need("utils", "for this test", version = "1.0"))
  expect_error(
    SAShiny:::.sashiny_need("utils", "for this test", version = "999.0"),
    "'utils' package 999.0 or later is required for this test"
  )
  expect_error(
    SAShiny:::.sashiny_need("notapackage123", "for this test"),
    "'notapackage123' package is required for this test"
  )
})
