# Conformance tests for deployment targets (spec section 6.8,
# spec/fixtures/deploy). Generating writes only under tempdir().

# The deployment fixtures hold hidden files (.dockerignore), which CRAN does
# not accept in a package, so they are read from the repository's spec/ only;
# the golden-file tests skip in an installed or CRAN build.
deploy_fixtures <- function() file.path(dirname(.sashiny_fixtures()), "fixtures", "deploy")

skip_without_deploy_fixtures <- function() {
  skip_if_not(dir.exists(deploy_fixtures()), "deploy fixtures are only in the source repository")
}

read_json_fixture <- function(...) {
  jsonlite::fromJSON(file.path(deploy_fixtures(), ...), simplifyVector = FALSE)
}

as_env <- function(pairs) {
  stats::setNames(vapply(pairs, function(p) p[[2]], ""), vapply(pairs, function(p) p[[1]], ""))
}

stage_app <- function(case_dir, add_files = list()) {
  app <- tempfile("sashiny-app-")
  dir.create(app)
  src <- file.path(case_dir, "app")
  files <- list.files(src, recursive = TRUE, all.files = TRUE, no.. = TRUE)
  for (f in files) {
    dir.create(dirname(file.path(app, f)), recursive = TRUE, showWarnings = FALSE)
    file.copy(file.path(src, f), file.path(app, f))
  }
  for (rel in names(add_files)) {
    dir.create(dirname(file.path(app, rel)), recursive = TRUE, showWarnings = FALSE)
    writeBin(charToRaw(add_files[[rel]]), file.path(app, rel))
  }
  app
}

test_that("profiles match the shared fixture (spec section 6.8)", {
  skip_without_deploy_fixtures()
  for (case in read_json_fixture("profiles.json")$cases) {
    if (!is.null(case$expected_error)) {
      expect_error(sas_profile(case$profile), paste0("^", case$expected_error), info = case$name)
      next
    }
    p <- sas_profile(case$profile)
    exp <- case$expected
    expect_identical(p$kind, exp$kind, info = case$name)
    expect_identical(p$endpoints, unlist(exp$endpoints), info = case$name)
    expect_identical(p$needs_java, exp$needs_java, info = case$name)
    expect_identical(p$requires_vpn, exp$requires_vpn, info = case$name)
    expect_identical(p$env, as_env(exp$env), info = case$name)
    expect_identical(p$secrets, as.character(unlist(exp$secrets)), info = case$name)
  }
})

test_that("generate() matches every golden-file case byte for byte", {
  skip_without_deploy_fixtures()
  cases <- list.dirs(deploy_fixtures(), recursive = FALSE)
  cases <- cases[file.exists(file.path(cases, "case.json"))]
  expect_gt(length(cases), 0L)
  for (case_dir in cases) {
    case <- jsonlite::fromJSON(file.path(case_dir, "case.json"), simplifyVector = FALSE)
    app <- stage_app(case_dir, case$add_files)
    out <- tempfile("sashiny-out-")
    res <- do.call(sas_deploy, c(
      list(app, case$target, out, profile = case$profile,
           license_ack = case$license_ack, version = case$version),
      case$options
    ))
    exp <- case$expected
    name <- basename(case_dir)
    expect_identical(res$language, exp$language, info = name)
    expect_identical(res$files, as.character(unlist(exp$files)), info = name)
    expect_identical(res$excluded, as.character(unlist(exp$excluded)), info = name)
    expect_identical(res$env, as_env(exp$env), info = name)
    expect_identical(res$secrets, as.character(unlist(exp$secrets)), info = name)
    expect_identical(res$endpoints, as.character(unlist(exp$endpoints)), info = name)
    written <- sort(list.files(out, recursive = TRUE, all.files = TRUE, no.. = TRUE), method = "radix")
    expect_identical(written, as.character(unlist(exp$files)), info = name)
    want_dir <- file.path(case_dir, "expected")
    for (rel in list.files(want_dir, recursive = TRUE, all.files = TRUE, no.. = TRUE)) {
      want <- readBin(file.path(want_dir, rel), "raw", n = 1e6)
      got <- readBin(file.path(out, rel), "raw", n = 1e6)
      expect_identical(got, want, info = paste(name, rel))
    }
    for (f in list.files(out, recursive = TRUE, full.names = TRUE)) {
      expect_false(any(grepl("placeholder credential", readLines(f, warn = FALSE), fixed = TRUE)))
    }
  }
})

test_that("generate() errors match the shared fixture", {
  skip_without_deploy_fixtures()
  for (case in read_json_fixture("errors.json")$cases) {
    app <- stage_app(file.path(deploy_fixtures(), dirname(case$app)))
    run <- function() {
      do.call(sas_deploy, c(
        list(app, case$target, tempfile("sashiny-out-"), profile = case$profile,
             license_ack = case$license_ack, version = "0.0.0"),
        case$options
      ))
    }
    if (is.null(case$expected_error)) {
      expect_gt(length(run()$files), 0L)
    } else {
      expect_error(run(), paste0("^", case$expected_error), info = case$name)
    }
  }
})

test_that("out_dir must be empty and the registry lists container", {
  skip_without_deploy_fixtures()
  app <- stage_app(file.path(deploy_fixtures(), "vpn_rejected"))
  out <- tempfile("sashiny-out-")
  dir.create(out)
  writeLines("x", file.path(out, "old.txt"))
  expect_error(
    sas_deploy(app, "container", out, profile = list(name = "oda", method = "iom", oda_region = "us1"),
               license_ack = TRUE),
    "out_dir must be empty"
  )
  expect_true("container" %in% sas_deploy_targets()$id)
  expect_error(sas_deploy_doctor("heroku"), "unknown deployment target")
  expect_type(sas_deploy_doctor("container"), "character")
})

test_that("apply runs through the injected runner", {
  .sashiny_register_target(list(
    id = "zz_test", label = "test", languages = c("python", "r"), options = character(0),
    generate = function(ctx) list("x.txt" = "x\n"),
    apply = function(ctx, result, runner) {
      cmd <- c("echo", ctx$profile$kind)
      runner(cmd, c(SASHINY_LICENSE_ACK = "true"))
      list(cmd)
    }
  ))
  on.exit(rm("zz_test", envir = .sashiny_targets), add = TRUE)
  calls <- list()
  runner <- function(args, env) {
    calls[[length(calls) + 1L]] <<- list(args = args, env = env)
    0L
  }
  app <- tempfile("sashiny-app-")
  dir.create(app)
  writeLines("library(SAShiny)", file.path(app, "app.R"))
  res <- sas_deploy(app, "zz_test", tempfile("sashiny-out-"),
    profile = list(name = "oda", method = "iom", oda_region = "us1"),
    license_ack = TRUE, apply = TRUE, runner = runner
  )
  expect_identical(res$commands, list(c("echo", "oda")))
  expect_identical(calls[[1]]$args, c("echo", "oda"))
})

test_that("sas_connect_env() builds the engine from deployment variables", {
  withr::local_envvar(
    SASHINY_PROFILE = NA, SASHINY_ODA_REGION = NA, SASHINY_VIYA_URL = NA,
    SASHINY_SAS94_HOST = NA, SASHINY_SAS94_PORT = NA, SASHINY_SAS94_SASPATH = NA
  )
  expect_error(sas_connect_env(), "SASHINY_PROFILE")
  withr::local_envvar(SASHINY_PROFILE = "oda", SASHINY_ODA_REGION = "eu1")
  expect_identical(sas_connect_env()$backend, "oda")
  withr::local_envvar(SASHINY_PROFILE = "viya")
  expect_error(sas_connect_env(), "SASHINY_VIYA_URL")
  withr::local_envvar(SASHINY_VIYA_URL = "https://viya.example.com")
  expect_identical(sas_connect_env()$backend, "viya")
  withr::local_envvar(SASHINY_PROFILE = "sas94", SASHINY_SAS94_HOST = "sas94.example.com",
                      SASHINY_SAS94_PORT = "8592")
  engine <- sas_connect_env(license_ack = TRUE)
  expect_identical(engine$backend, "sas94-iom")
  expect_identical(engine$cfg$iomport, 8592L)
})

test_that("the container Dockerfile follows the spec without the fixtures", {
  app <- tempfile("sashiny-app-")
  dir.create(app)
  writeLines("library(SAShiny)", file.path(app, "app.R"))
  writeLines("secret", file.path(app, ".authinfo"))
  out <- tempfile("sashiny-out-")
  res <- sas_deploy(app, "container", out,
    profile = list(name = "oda", method = "iom", oda_region = "us1"),
    license_ack = TRUE, version = "0.0.0", port = 3838L
  )
  expect_identical(res$files, c(".dockerignore", "Dockerfile", "bundle/app.R"))
  expect_identical(res$excluded, ".authinfo")
  docker <- readLines(file.path(out, "Dockerfile"))
  expect_true(any(grepl("openjdk-17-jre-headless", docker, fixed = TRUE)))
  expect_true("USER sashiny" %in% docker)
  expect_true("EXPOSE 3838" %in% docker)
  expect_true(any(startsWith(docker, "HEALTHCHECK")))
  expect_false(any(grepl("SASHINY_SAS", docker, fixed = TRUE)))
  expect_error(
    sas_deploy(app, "container", tempfile(),
      profile = list(name = "v", method = "http", url = "https://v.example.com", requires_vpn = TRUE),
      license_ack = TRUE
    ),
    "^profile v requires a private network"
  )
})

test_that("bundle files skip nested metadata folders and sort by bytes", {
  app <- tempfile("sashiny-bundle-")
  for (f in c("b.R", "a/x.R", "a/.git/HEAD", "sub/__pycache__/m.pyc", "Z.R", "keys/id.key")) {
    dir.create(dirname(file.path(app, f)), recursive = TRUE, showWarnings = FALSE)
    writeLines("x", file.path(app, f))
  }
  res <- .sashiny_bundle_files(app)
  expect_identical(res$files, c("Z.R", "a/x.R", "b.R"))
  expect_identical(res$excluded, "keys/id.key")
})
