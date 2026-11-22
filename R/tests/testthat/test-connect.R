# Backend constructors and sas_connect() (spec section 6.6, #130 H3).

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

test_that("each profile maps to a supported backend (spec section 6.6)", {
  expect_identical(sas_connect("oda")$backend, "oda")
  expect_identical(sas_connect("viya", url = "https://v.example.com")$backend, "viya")
  expect_identical(sas_connect("sas94", host = "h.example.com")$backend, "sas94-iom")
  expect_identical(
    sas_connect("sas94", host = "h.example.com", saspath = "/opt/sas")$backend, "sas94-ssh"
  )
  expect_true(sas_connect("oda", license_ack = TRUE)$license_ack)
})

test_that("sas_engine_saspy accepts only SAS 9.4, Viya and ODA configurations", {
  expect_identical(sas_engine_saspy("/path/to/sascfg_personal.py")$backend, "cfgfile")
  expect_error(sas_engine_saspy(list(provider = "sas.iomprovider")), "COM")
  expect_error(sas_engine_saspy(list(saspath = "/opt/sas/sas")), "STDIO")
  expect_error(sas_engine_saspy(list()), "named list")
  expect_error(sas_engine_saspy(list(java = "java")), "exactly one connection")
  expect_error(sas_engine_saspy(list(url = "viya.example.com")), "https://")
  expect_error(sas_engine_saspy(list(url = "https://v", iomhost = "h")), "exactly one")
  expect_error(sas_engine_saspy(list(iomhost = c("a", "b"))), "exactly one iomhost")
  expect_false("session_factory" %in% names(formals(sas_engine_saspy)))
})

test_that("SAS credentials from the environment become saspy keyword arguments (spec 6.7)", {
  withr::local_envvar(SASHINY_SAS_USER = "me", SASHINY_SAS_PASSWORD = "pw")
  expect_identical(.sashiny_env_credentials(list(iomhost = "h")), list(omruser = "me", omrpw = "pw"))
  expect_identical(.sashiny_env_credentials(list(url = "https://v")), list(user = "me", pw = "pw"))
  expect_identical(.sashiny_env_credentials(list(saspath = "/s", host = "h")), list())
  withr::local_envvar(SASHINY_SAS_PASSWORD = NA)
  expect_identical(.sashiny_env_credentials(list(iomhost = "h")), list())
})
test_that("each backend constructor builds the same configuration as the old form", {
  withr::local_options(lifecycle_verbosity = "quiet")
  expect_identical(sas_connect(sas_oda("eu1"))$cfg, sas_connect("oda", region = "eu1")$cfg)
  expect_identical(sas_connect(sas_viya("https://v.example.com", context = "c"))$cfg,
    sas_connect("viya", url = "https://v.example.com", context = "c")$cfg)
  expect_identical(sas_connect(sas_94_iom("h.example.com", port = 1234))$cfg,
    sas_connect("sas94", host = "h.example.com", port = 1234L)$cfg)
  expect_identical(sas_connect(sas_94_ssh("h.example.com", "/opt/sas", ssh_user = "me"))$cfg,
    sas_connect("sas94", host = "h.example.com", saspath = "/opt/sas", ssh_user = "me")$cfg)
  expect_identical(sas_connect(sas_94_ssh("h.example.com", "/opt/sas"))$backend, "sas94-ssh")
})

test_that("constructors validate their own arguments", {
  expect_error(sas_oda("xx9"), "unknown ODA region xx9", class = "sashiny_error_engine")
  expect_error(sas_viya("viya.example.com"), "must be one 'SAS Viya' URL", class = "sashiny_error_engine")
  expect_error(sas_viya("https://v", verify = NA), "verify must be TRUE or FALSE")
  expect_error(sas_94_iom(""), "host must be one", class = "sashiny_error_engine")
  expect_error(sas_94_iom("h", port = 70000), "port must be an integer")
  expect_error(sas_94_ssh("h", ""), "saspath must be")
  expect_error(sas_connect(list()), "backend must come from")
  expect_error(sas_connect(sas_oda(), region = "eu1"), "go to the backend constructor")
})

test_that("the old profile form still works and is deprecated", {
  withr::local_options(lifecycle_verbosity = "warning")
  expect_warning(e <- sas_connect("oda", region = "us1"), class = "lifecycle_warning_deprecated")
  expect_identical(e$backend, "oda")
  expect_output(print(sas_oda("ap1")), "<sashiny backend> oda (ap1)", fixed = TRUE)
})
