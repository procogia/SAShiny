# Tests for the opt-in result cache (spec section 6.11).

.cache_contract <- function(...) {
  contract <- sas_contract(file.path(.sashiny_fixtures(), "contracts", "valid",
                                     "result_cache", "contract.sashiny.yml"))
  run <- list(...)
  for (n in names(run)) contract$data$run[[n]] <- run[[n]]
  contract
}

.counting_engine <- function(status = NULL) {
  engine <- .sashiny_engine_mock()
  calls <- 0L
  structure(list(
    inner = engine,
    status = status,
    calls = function() calls,
    bump = function() calls <<- calls + 1L
  ), class = "sashiny_test_counting")
}

sas_engine_run.sashiny_test_counting <- function(engine, contract, values, today = Sys.Date(),
                                                 uploads = NULL, run_id = NULL) {
  engine$bump()
  res <- sas_engine_run(engine$inner, contract, values, today = today, uploads = uploads,
    run_id = run_id)
  if (!is.null(engine$status) && identical(res$status, "success")) res$status <- engine$status
  res
}

sas_engine_choices.sashiny_test_counting <- function(engine, contract) list()

registerS3method("sas_engine_run", "sashiny_test_counting", sas_engine_run.sashiny_test_counting,
  envir = asNamespace("SAShiny"))
registerS3method("sas_engine_choices", "sashiny_test_counting",
  sas_engine_choices.sashiny_test_counting, envir = asNamespace("SAShiny"))

local_fresh_cache <- function(env = parent.frame()) {
  previous <- .sashiny_cache_set_store(NULL)
  withr::defer(.sashiny_cache_set_store(previous), envir = env)
}

today <- as.Date("2026-11-11")

test_that("the cache key text matches the hand-written fixture", {
  k <- jsonlite::read_json(file.path(.sashiny_fixtures(), "collect", "cache_key.json"))
  macros <- stats::setNames(
    lapply(k$macros, function(m) m[[2]]), vapply(k$macros, function(m) m[[1]], "")
  )
  uploads <- stats::setNames(
    vapply(k$uploads, function(u) u[[2]], ""), vapply(k$uploads, function(u) u[[1]], "")
  )
  text <- .sashiny_cache_key_text(k$contract_sha256, k$program_sha256, macros, uploads)
  expect_identical(text, k$key_text)
  expect_identical(.sashiny_sha256(charToRaw(enc2utf8(text))), k$key)
})

test_that("identical runs hit the cache and keep their run id", {
  local_fresh_cache()
  engine <- .counting_engine()
  contract <- .cache_contract()
  first <- sas_run(contract, engine, list(n = 1), today = today)
  expect_null(first$metadata$cache_hit)
  again <- sas_run(contract, engine, list(n = 1), today = today)
  expect_identical(engine$calls(), 1L)
  expect_identical(again$run_id, first$run_id)
  expect_true(again$metadata$cache_hit)
  expect_match(again$metadata$cached_at, "Z$")
  other <- sas_run(contract, engine, list(n = 2), today = today)
  expect_identical(engine$calls(), 2L)
  expect_false(identical(other$run_id, first$run_id))
})

test_that("the cache is off by default", {
  local_fresh_cache()
  engine <- .counting_engine()
  contract <- .cache_contract(cache = FALSE)
  sas_run(contract, engine, list(n = 1), today = today)
  sas_run(contract, engine, list(n = 1), today = today)
  expect_identical(engine$calls(), 2L)
})

test_that("cached results expire after cache_ttl_seconds", {
  local_fresh_cache()
  engine <- .counting_engine()
  contract <- .cache_contract(cache_ttl_seconds = 10L)
  sas_run(contract, engine, list(n = 1), today = today)
  found <- .sashiny_cache_lookup(engine, contract, list(n = 1), today)
  entry <- .sashiny_cache_store()$get(found$key)
  .sashiny_cache_store()$set(found$key, entry$result, entry$stored_at - 11)
  sas_run(contract, engine, list(n = 1), today = today)
  expect_identical(engine$calls(), 2L)
})

test_that("error and timeout results are not cached; warnings are", {
  for (status in c("error", "timeout")) {
    local_fresh_cache()
    engine <- .counting_engine(status)
    sas_run(.cache_contract(), engine, list(n = 1), today = today)
    sas_run(.cache_contract(), engine, list(n = 1), today = today)
    expect_identical(engine$calls(), 2L)
  }
  local_fresh_cache()
  engine <- .counting_engine("warning")
  sas_run(.cache_contract(), engine, list(n = 1), today = today)
  hit <- sas_run(.cache_contract(), engine, list(n = 1), today = today)
  expect_identical(engine$calls(), 1L)
  expect_identical(hit$status, "warning")
})

test_that("invalid values bypass the cache", {
  local_fresh_cache()
  engine <- .counting_engine()
  bad <- sas_run(.cache_contract(), engine, list(n = 99), today = today)
  expect_identical(bad$status, "error")
  expect_identical(.sashiny_cache_store()$size(), 0L)
})

test_that("changed upload bytes miss the cache", {
  local_fresh_cache()
  dir <- withr::local_tempdir()
  file.copy(file.path(.sashiny_fixtures(), "contracts", "valid", "dataset"), dir, recursive = TRUE)
  contract <- sas_contract(file.path(dir, "dataset", "contract.sashiny.yml"))
  contract$data$run <- list(cache = TRUE)
  upload <- file.path(dir, "adsl.csv")
  writeLines(c("USUBJID,AGE,TRTSDT", "A,30,2024-01-01"), upload)
  engine <- .counting_engine()
  sas_run(contract, engine, list(), today = today, uploads = list(adsl = upload))
  sas_run(contract, engine, list(), today = today, uploads = list(adsl = upload))
  expect_identical(engine$calls(), 1L)
  writeLines(c("USUBJID,AGE,TRTSDT", "B,40,2024-01-01"), upload)
  sas_run(contract, engine, list(), today = today, uploads = list(adsl = upload))
  expect_identical(engine$calls(), 2L)
})

test_that("the LRU store evicts the least recently used result", {
  local_fresh_cache()
  .sashiny_cache_set_store(.sashiny_lru_store(2L))
  engine <- .counting_engine()
  for (n in 1:3) sas_run(.cache_contract(), engine, list(n = n), today = today)
  expect_identical(.sashiny_cache_store()$size(), 2L)
  sas_run(.cache_contract(), engine, list(n = 1), today = today)
  expect_identical(engine$calls(), 4L)
  expect_error(.sashiny_lru_store(0), "max_entries")
})