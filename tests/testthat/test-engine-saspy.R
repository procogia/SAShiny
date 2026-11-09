# Tests for the saspy engine interface (issue #6).
#
# These tests exercise the parts that do not require a live SAS session: profile
# loading and log classification/status. Live verification is deferred to #11.

test_that("load_profiles defaults to offline", {
  profiles <- sas_load_profiles(file.path(tempdir(), "missing.yml"))
  expect_identical(profiles$default, "offline")
  expect_identical(profiles$profiles, list())
})

test_that("load_profiles reads a file", {
  path <- tempfile(fileext = ".yml")
  writeLines("default: oda\nprofiles:\n  oda:\n    method: iom\n    oda_region: us1\n",
             path)
  on.exit(unlink(path), add = TRUE)
  profiles <- sas_load_profiles(path)
  expect_identical(profiles$default, "oda")
  expect_identical(profiles$profiles$oda$method, "iom")
})

test_that("run_status classifies success", {
  st <- .sashiny_run_status("NOTE: SASHINY-END run=fixture syscc=0\n")
  expect_identical(st$status, "success")
  expect_identical(st$syscc, 0L)
})

test_that("run_status reports error on missing sentinel", {
  st <- .sashiny_run_status("NOTE: nothing here")
  expect_identical(st$status, "error")
  expect_null(st$syscc)
})

test_that("run_status reports error on high syscc", {
  st <- .sashiny_run_status("NOTE: SASHINY-END run=fixture syscc=3000\n")
  expect_identical(st$status, "error")
  expect_identical(st$syscc, 3000L)
})