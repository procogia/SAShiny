test_that("package metadata is in place", {
  desc <- utils::packageDescription("SAShiny")
  expect_identical(desc$Package, "SAShiny")
  expect_match(desc$License, "^MIT")
})
