# Conformance tests for the contract loader and validator (issue #1).
#
# Reads spec/fixtures/contracts and asserts the same behaviour as the
# reference oracle: valid contracts produce no issues; invalid contracts
# produce the exact {code, path} set (schema E000: at least the listed paths).

test_that("valid contracts produce no issues", {
  fix <- .sashiny_fixtures()
  valid_dir <- file.path(fix, "contracts", "valid")
  dirs <- list.dirs(valid_dir, recursive = FALSE)
  for (d in dirs) {
    yml <- file.path(d, "contract.sashiny.yml")
    contract <- sas_contract(yml)
    issues <- sas_validate(contract, .sashiny_today)
    info <- paste(vapply(issues, function(i) paste(i$code, i$path, i$message), character(1)),
                  collapse = "; ")
    expect_true(length(issues) == 0L,
                info = paste0(basename(d), ": ", info))
  }
})

test_that("invalid contracts produce the expected issues", {
  fix <- .sashiny_fixtures()
  invalid_dir <- file.path(fix, "contracts", "invalid")
  dirs <- list.dirs(invalid_dir, recursive = FALSE)
  for (d in dirs) {
    yml <- file.path(d, "contract.sashiny.yml")
    expected <- jsonlite::fromJSON(file.path(d, "expected.json"), simplifyVector = FALSE)
    want <- lapply(expected$errors, function(e) c(e$code, e$path))
    contract <- sas_contract(yml)
    got_issues <- sas_validate(contract, .sashiny_today)
    got <- lapply(got_issues, function(i) c(i$code, i$path))

    if (all(vapply(want, function(w) w[[1]] == "E000", logical(1)))) {
      # Schema errors: the expected path must be reported; exact messages vary.
      paths_found <- all(vapply(want, function(w) {
        any(vapply(got, function(g) startsWith(g[[2]], w[[2]]) || startsWith(w[[2]], g[[2]]),
                   logical(1)))
      }, logical(1)))
      expect_true(length(got) > 0L, info = basename(d))
      expect_true(all(vapply(got, function(g) g[[1]] == "E000", logical(1))),
                  info = basename(d))
      expect_true(paths_found, info = basename(d))
    } else {
      got_s <- sort(vapply(got, function(g) paste(g, collapse = "\r"), character(1)))
      want_s <- sort(vapply(want, function(w) paste(w, collapse = "\r"), character(1)))
      expect_identical(got_s, want_s, info = basename(d))
    }
  }
})

test_that("one-sided date bounds are valid (issue #70)", {
  dir <- tempfile("sashiny-")
  dir.create(dir)
  writeLines("data work.out; run;", file.path(dir, "program.sas"))
  for (kind in c("date", "daterange")) {
    for (bound in c("min", "max")) {
      data <- list(
        sashiny = 1L, program = "program.sas", title = "t",
        inputs = list(x = list(type = kind, label = "X")),
        outputs = list(log = list(type = "log"))
      )
      data$inputs$x[[bound]] <- "2026-01-01"
      contract <- structure(list(data = data, base_dir = dir), class = "sashiny_contract")
      expect_true(length(sas_validate(contract, .sashiny_today)) == 0L)
    }
  }
})

test_that("a present-but-invalid one-sided date bound is S003", {
  dir <- tempfile("sashiny-")
  dir.create(dir)
  writeLines("data work.out; run;", file.path(dir, "program.sas"))
  data <- list(
    sashiny = 1L, program = "program.sas", title = "t",
    inputs = list(x = list(type = "date", label = "X", min = "2026-02-30")),
    outputs = list(log = list(type = "log"))
  )
  contract <- structure(list(data = data, base_dir = dir), class = "sashiny_contract")
  issues <- sas_validate(contract, .sashiny_today)
  expect_true(any(vapply(issues, function(i) i$code == "S003" && i$path == "/inputs/x",
                         logical(1))))
})

test_that("literal character classes are portable (issue #82)", {
  dir <- tempfile("sashiny-")
  dir.create(dir)
  writeLines("data work.out; run;", file.path(dir, "program.sas"))
  for (pattern in c("[+?]", "[(?=]", "[*+]", "[a-z+?]")) {
    data <- list(
      sashiny = 1L, program = "program.sas", title = "t",
      inputs = list(x = list(type = "text", label = "X", pattern = pattern)),
      outputs = list(log = list(type = "log"))
    )
    contract <- structure(list(data = data, base_dir = dir), class = "sashiny_contract")
    expect_true(length(sas_validate(contract, .sashiny_today)) == 0L, info = pattern)
  }
})

test_that("a forbidden construct outside a class is S014", {
  dir <- tempfile("sashiny-")
  dir.create(dir)
  writeLines("data work.out; run;", file.path(dir, "program.sas"))
  data <- list(
    sashiny = 1L, program = "program.sas", title = "t",
    inputs = list(x = list(type = "text", label = "X", pattern = "a+?")),
    outputs = list(log = list(type = "log"))
  )
  contract <- structure(list(data = data, base_dir = dir), class = "sashiny_contract")
  issues <- sas_validate(contract, .sashiny_today)
  expect_true(any(vapply(issues, function(i) i$code == "S014" && i$path == "/inputs/x/pattern",
                         logical(1))))
})

test_that("schema validation preserves fractional numeric properties (issue #83)", {
  dir <- tempfile("sashiny-")
  dir.create(dir)
  writeLines("data work.out; run;", file.path(dir, "program.sas"))
  data <- list(
    sashiny = 1L, program = "program.sas", title = "t",
    inputs = list(x = list(type = "text", label = "X", max_length = 1.000001)),
    outputs = list(log = list(type = "log"))
  )
  contract <- structure(list(data = data, base_dir = dir), class = "sashiny_contract")
  issues <- sas_validate(contract, .sashiny_today)
  expect_true(any(vapply(issues, function(i) i$code == "E000", logical(1))))
})
# Spec section 1.1 plain scalar typing (#155), mirrored in Python/tests/test_contracts.py.
yaml_scalars <- list(
  list("-.5", -0.5),
  list("+.5", 0.5),
  list(".5", 0.5),
  list("1.", 1),
  list("1.5e+3", 1500),
  list("-.5E-3", -0.0005),
  list("-.inf", -Inf),
  list("12", 12L),
  list("+12", 12L),
  list("0x1A", 26L),
  list("2147483648", 2147483648),
  list("1_000", "1_000"),
  list("1,000", "1,000"),
  list("017", "017"),
  list("08", "08"),
  list("1e3", "1e3"),
  list("1.5e3", "1.5e3"),
  list("0o17", "0o17"),
  list("0b101", "0b101"),
  list("-0x1A", "-0x1A"),
  list("1:30", "1:30"),
  list("y", "y"),
  list("yes", TRUE),
  list("off", FALSE),
  list("~", NULL)
)

test_that("plain scalars are typed by the shared rule (spec section 1.1, #155)", {
  dir <- withr::local_tempdir()
  path <- file.path(dir, "x.sashiny.yml")
  for (case in yaml_scalars) {
    writeLines(paste0("v: ", case[[1]]), path)
    expect_identical(sas_contract(path)$data$v, case[[2]], info = case[[1]])
  }
})
