# Tests for the SAS connection selection (issue #6).

test_that("sas_connect oda builds the config", {
  engine <- sas_connect("oda", region = "us1")
  expect_identical(engine$cfg$iomhost, .sashiny_oda_hosts$us1)
  expect_identical(engine$cfg$iomport, 8591L)
  expect_identical(engine$cfg$authkey, "oda")
  expect_identical(engine$cfg$encoding, "utf-8")
})

test_that("sas_connect oda rejects an unknown region", {
  expect_error(sas_connect("oda", region = "xx9"), "unknown ODA region")
})

test_that("sas_connect viya requires url", {
  expect_error(sas_connect("viya"), "url is required")
})

test_that("sas_connect viya builds the config", {
  engine <- sas_connect("viya", url = "https://viya.example.com",
                        context = "SAS Studio compute context")
  expect_identical(engine$cfg$url, "https://viya.example.com")
  expect_identical(engine$cfg$authkey, "viya")
  expect_identical(engine$cfg$context, "SAS Studio compute context")
})

test_that("sas_connect sas94 IOM builds the config", {
  engine <- sas_connect("sas94", host = "sas.example.com", port = 8591L)
  expect_identical(engine$cfg$iomhost, "sas.example.com")
  expect_identical(engine$cfg$iomport, 8591L)
  expect_identical(engine$cfg$authkey, "iom")
})

test_that("sas_connect sas94 SSH builds the config", {
  engine <- sas_connect("sas94", host = "sas.example.com",
                        saspath = "/opt/sas/sas_u8", ssh_user = "me")
  expect_identical(engine$cfg$saspath, "/opt/sas/sas_u8")
  expect_identical(engine$cfg$host, "sas.example.com")
  expect_identical(engine$cfg$luser, "me")
})

test_that("sas_connect sas94 requires host", {
  expect_error(sas_connect("sas94"), "host is required")
})

test_that("sas_connect rejects an unknown profile", {
  expect_error(sas_connect("bogus"), "unknown profile")
})