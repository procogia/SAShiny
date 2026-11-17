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
    if (case$target %in% c("streamlit_snowflake", "databricks_apps")) next # Python only (6.8.5, 6.8.6)
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

az_app <- function() {
  app <- tempfile("sashiny-az-app-")
  dir.create(app)
  writeLines("library(shiny)", file.path(app, "app.R"))
  app
}
az_oda <- list(name = "oda", method = "iom", oda_region = "us1")

test_that("azure apply runs az through the runner (spec section 6.8.1)", {
  calls <- list()
  runner <- function(args, env) {
    calls[[length(calls) + 1L]] <<- args
    0L
  }
  res <- sas_deploy(az_app(), "azure_container_apps", tempfile("az-out-"), az_oda,
    license_ack = TRUE, apply = TRUE, runner = runner, version = "0.0.0",
    resource_group = "rg1", acr_name = "myacr", image_tag = "v1",
    sas_user_secret_uri = "https://kv.vault.azure.net/secrets/sashiny-sas-user",
    sas_password_secret_uri = "https://kv.vault.azure.net/secrets/sashiny-sas-password"
  )
  expect_equal(calls[[1]], c(
    "az", "acr", "build", "--registry", "myacr", "--image", "sashiny-app:v1", res$out_dir
  ))
  expect_equal(calls[[2]][1:6], c("az", "deployment", "group", "create", "--resource-group", "rg1"))
  expect_true("acrName=myacr" %in% calls[[2]])
  expect_equal(res$commands, calls)
})

test_that("azure apply needs its options and stops on a failed command", {
  expect_error(
    sas_deploy(az_app(), "azure_container_apps", tempfile(), az_oda,
      license_ack = TRUE, apply = TRUE, runner = function(a, e) 0L
    ),
    "apply needs the options resource_group, acr_name", fixed = TRUE
  )
  expect_error(
    sas_deploy(az_app(), "azure_container_apps", tempfile(), az_oda,
      license_ack = TRUE, apply = TRUE, runner = function(a, e) 1L,
      resource_group = "rg", acr_name = "a", sas_user_secret_uri = "u", sas_password_secret_uri = "p"
    ),
    "exit status 1"
  )
})

test_that("azure options are validated", {
  expect_error(
    sas_deploy(az_app(), "azure_container_apps", tempfile(), az_oda, license_ack = TRUE, app_name = "Bad_Name"),
    "app_name must be"
  )
  expect_error(
    sas_deploy(az_app(), "azure_container_apps", tempfile(), az_oda, license_ack = TRUE, max_replicas = 0),
    "max_replicas must be"
  )
  vpn <- list(name = "v", method = "http", url = "https://v.example.com", requires_vpn = TRUE)
  expect_error(
    sas_deploy(az_app(), "azure_container_apps", tempfile(), vpn, license_ack = TRUE),
    "profile v requires a private network; pass infrastructure_subnet_id", fixed = TRUE
  )
})

test_that("azure output for an ssh profile has no secrets", {
  prof <- list(name = "s", method = "ssh", host = "h.example.com", saspath = "/opt/sas/sas")
  res <- sas_deploy(az_app(), "azure_container_apps", tempfile(), prof, license_ack = TRUE)
  bicep <- paste(readLines(file.path(res$out_dir, "infra", "main.bicep")), collapse = "\n")
  expect_false(grepl("secrets:", bicep, fixed = TRUE))
  expect_false(grepl("SecretUri", bicep, fixed = TRUE))
  guide <- paste(readLines(file.path(res$out_dir, "deploy-azure.md")), collapse = "\n")
  expect_false(grepl("keyvault", guide, fixed = TRUE))
})

test_that("azure doctor reports a failed login by name", {
  skip_if_not(nzchar(Sys.which("az")), "az is not installed")
  expect_equal(sas_deploy_doctor("azure_container_apps", function(a, e) 1L), "az is not logged in (run az login)")
})

test_that("aws apply runs docker and aws through the runner (spec section 6.8.2)", {
  calls <- list()
  runner <- function(args, env) {
    calls[[length(calls) + 1L]] <<- args
    0L
  }
  image <- "1.dkr.ecr.us-east-1.amazonaws.com/sashiny-app:v1"
  res <- sas_deploy(az_app(), "aws_ecs_express", tempfile("aws-out-"), az_oda,
    license_ack = TRUE, apply = TRUE, runner = runner,
    image_uri = image, vpc_id = "vpc-1", public_subnet_ids = c("subnet-a", "subnet-b"),
    private_subnet_ids = "subnet-c,subnet-d", certificate_arn = "arn:aws:acm:us-east-1:1:certificate/x",
    sas_user_secret_arn = "arn:aws:secretsmanager:us-east-1:1:secret:u",
    sas_password_secret_arn = "arn:aws:secretsmanager:us-east-1:1:secret:p"
  )
  expect_equal(calls[[1]], c("docker", "build", "--platform", "linux/amd64", "-t", image, res$out_dir))
  expect_equal(calls[[2]], c("docker", "push", image))
  expect_equal(calls[[3]][1:5], c("aws", "cloudformation", "deploy", "--stack-name", "sashiny-app"))
  expect_true("PublicSubnetIds=subnet-a,subnet-b" %in% calls[[3]])
  expect_equal(res$commands, calls)
})

test_that("aws apply and options are validated", {
  expect_error(
    sas_deploy(az_app(), "aws_ecs_express", tempfile(), az_oda,
      license_ack = TRUE, apply = TRUE, runner = function(a, e) 0L
    ),
    "apply needs the options image_uri, vpc_id", fixed = TRUE
  )
  expect_error(
    sas_deploy(az_app(), "aws_ecs_express", tempfile(), az_oda, license_ack = TRUE, desired_count = 11),
    "desired_count must be"
  )
  vpn <- list(name = "v", method = "http", url = "https://v.example.com", requires_vpn = TRUE)
  expect_error(
    sas_deploy(az_app(), "aws_ecs_express", tempfile(), vpn, license_ack = TRUE),
    "pass private_network for target aws_ecs_express", fixed = TRUE
  )
})

test_that("aws output for an ssh profile has no secrets", {
  prof <- list(name = "s", method = "ssh", host = "h.example.com", saspath = "/opt/sas/sas")
  res <- sas_deploy(az_app(), "aws_ecs_express", tempfile(), prof, license_ack = TRUE)
  text <- paste(readLines(file.path(res$out_dir, "infra", "template.yaml")), collapse = "\n")
  expect_false(grepl("SecretArn", text, fixed = TRUE))
  expect_true(grepl("FromPort: 22\n", text, fixed = TRUE))
  guide <- paste(readLines(file.path(res$out_dir, "deploy-aws.md")), collapse = "\n")
  expect_false(grepl("secretsmanager", guide, fixed = TRUE))
  expect_true(grepl("## 1. Build and push the image", guide, fixed = TRUE))
})

test_that("snowflake apply runs snow and docker through the runner (spec section 6.8.3)", {
  calls <- list()
  runner <- function(args, env) {
    calls[[length(calls) + 1L]] <<- args
    0L
  }
  res <- sas_deploy(az_app(), "snowflake_spcs", tempfile("sf-out-"), az_oda,
    license_ack = TRUE, apply = TRUE, runner = runner,
    repository_url = "org-acct.registry.snowflakecomputing.com/sashiny_db/app/sashiny_repo/",
    connection = "dev"
  )
  out <- res$out_dir
  image <- "org-acct.registry.snowflakecomputing.com/sashiny_db/app/sashiny_repo/sashiny-app:latest"
  expect_equal(calls, list(
    c("snow", "sql", "-f", paste0(out, "/spcs/setup.sql"), "--connection", "dev"),
    c("snow", "spcs", "image-registry", "login", "--connection", "dev"),
    c("docker", "build", "--platform", "linux/amd64", "-t", image, out),
    c("docker", "push", image),
    c("snow", "sql", "-f", paste0(out, "/spcs/service.sql"), "--connection", "dev")
  ))
})

test_that("snowflake options are validated", {
  expect_error(
    sas_deploy(az_app(), "snowflake_spcs", tempfile(), az_oda,
      license_ack = TRUE, apply = TRUE, runner = function(a, e) 0L
    ),
    "apply needs the options repository_url", fixed = TRUE
  )
  expect_error(
    sas_deploy(az_app(), "snowflake_spcs", tempfile(), az_oda, license_ack = TRUE, database = "db; DROP"),
    "database must be 1-63 uppercase"
  )
  vpn <- list(name = "v", method = "http", url = "https://v.example.com", requires_vpn = TRUE)
  expect_error(
    sas_deploy(az_app(), "snowflake_spcs", tempfile(), vpn, license_ack = TRUE),
    "pass private_connectivity for target snowflake_spcs", fixed = TRUE
  )
})

test_that("snowflake output for an ssh profile has no secret", {
  prof <- list(name = "s", method = "ssh", host = "h.example.com", saspath = "/opt/sas/sas")
  res <- sas_deploy(az_app(), "snowflake_spcs", tempfile(), prof, license_ack = TRUE, public = FALSE)
  expect_false("spcs/secret.sql" %in% res$files)
  spec <- paste(readLines(file.path(res$out_dir, "spcs", "service-spec.yaml")), collapse = "\n")
  expect_false(grepl("secrets:", spec, fixed = TRUE))
  expect_true(grepl("public: false", spec, fixed = TRUE))
})

test_that("posit_snowflake apply reuses sas_publish (spec section 6.8.4)", {
  app <- az_app()
  calls <- new.env()
  local_mocked_bindings(.sashiny_rsconnect = function() list(
    deployApp = function(...) {
      args <- list(...)
      args$profile_at_deploy <- Sys.getenv("SASHINY_PROFILE")
      calls$deploy <- args
      "deployed"
    }
  ))
  withr::local_envvar(
    SASHINY_SAS_USER = "me", SASHINY_SAS_PASSWORD = "pw", SASHINY_PROFILE = NA,
    CONNECT_SERVER = NA, CONNECT_API_KEY = NA
  )
  res <- sas_deploy(app, "posit_snowflake", tempfile("ps-out-"), az_oda,
    license_ack = TRUE, apply = TRUE, server = "spcs", title = "Cars"
  )
  expect_equal(calls$deploy$server, "spcs")
  expect_equal(calls$deploy$appTitle, "Cars")
  expect_equal(calls$deploy$envVars, c(
    "SASHINY_LICENSE_ACK", "SASHINY_PROFILE", "SASHINY_ODA_REGION",
    "SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD"
  ))
  expect_equal(calls$deploy$profile_at_deploy, "oda")
  expect_equal(Sys.getenv("SASHINY_PROFILE", unset = NA), NA_character_)
  expect_true(endsWith(res$commands[[1]][[2]], "bundle"))
})

test_that("posit_snowflake apply errors", {
  withr::local_envvar(CONNECT_SERVER = NA, CONNECT_API_KEY = NA)
  expect_error(
    sas_deploy(az_app(), "posit_snowflake", tempfile(), az_oda, license_ack = TRUE, apply = TRUE),
    "apply needs the option server or the environment variables", fixed = TRUE
  )
  py <- tempfile("pyapp-")
  dir.create(py)
  writeLines("import shiny", file.path(py, "app.py"))
  expect_error(
    sas_deploy(py, "posit_snowflake", tempfile(), az_oda, license_ack = TRUE, apply = TRUE, server = "s"),
    "apply for a Python app must run in Python", fixed = TRUE
  )
  withr::local_envvar(CONNECT_API_KEY = "k3y-value")
  problems <- sas_deploy_doctor("posit_snowflake")
  expect_true("CONNECT_SERVER not set; or pass server" %in% problems)
  expect_false(any(grepl("k3y-value", problems, fixed = TRUE)))
})

test_that("streamlit_snowflake is Python only (spec section 6.8.5)", {
  viya <- list(name = "v", method = "http", url = "https://v.example.com")
  expect_error(
    sas_deploy(az_app(), "streamlit_snowflake", tempfile(), viya, license_ack = TRUE),
    "target streamlit_snowflake does not support language r", fixed = TRUE
  )
  py <- tempfile("pyapp-")
  dir.create(py)
  writeLines("import shiny", file.path(py, "app.py"))
  expect_error(
    sas_deploy(py, "streamlit_snowflake", tempfile(), viya, license_ack = TRUE),
    "generated by the Python package", fixed = TRUE
  )
  expect_error(
    sas_deploy(py, "streamlit_snowflake", tempfile(), az_oda, license_ack = TRUE),
    "target streamlit_snowflake cannot provide Java 17", fixed = TRUE
  )
})

test_that("databricks_apps is Python only (spec section 6.8.6)", {
  viya <- list(name = "v", method = "http", url = "https://v.example.com")
  expect_error(
    sas_deploy(az_app(), "databricks_apps", tempfile(), viya, license_ack = TRUE),
    "target databricks_apps does not support language r", fixed = TRUE
  )
  py <- tempfile("pyapp-")
  dir.create(py)
  writeLines("import shiny", file.path(py, "app.py"))
  expect_error(
    sas_deploy(py, "databricks_apps", tempfile(), viya, license_ack = TRUE),
    "generated by the Python package", fixed = TRUE
  )
})

test_that("the deploy addin generates through sas_deploy and reports errors", {
  skip_if_not_installed("shiny")
  calls <- new.env()
  fake <- function(app_dir, target, ...) {
    calls$args <- list(app_dir = app_dir, target = target, ...)
    if (!isTRUE(calls$args$license_ack)) stop("deploying requires license_ack = TRUE")
    list(files = c("Dockerfile", "bundle/app.R"), excluded = ".authinfo", out_dir = "out")
  }
  shiny::testServer(.sashiny_deploy_server, args = list(deploy = fake), {
    session$setInputs(
      app_dir = "x", target = "container", method = "http",
      detail = "https://viya.example.com", private = FALSE, license_ack = FALSE
    )
    session$setInputs(deploy = 1)
    expect_match(output$status, "Generate failed: deploying requires")
    session$setInputs(license_ack = TRUE, private = TRUE, deploy = 2)
    expect_match(output$status, "Wrote 2 files to out. Not bundled: .authinfo", fixed = TRUE)
    expect_true(calls$args$private_network)
    expect_true(calls$args$profile$requires_vpn)
    expect_identical(calls$args$profile$url, "https://viya.example.com")
  })
})
