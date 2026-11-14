Sys.setenv(NOT_CRAN="true", SASHINY_LIVE="0")
pkgload::load_all("/tmp/SAShiny/R", quiet=TRUE)
result <- testthat::test_dir("/tmp/SAShiny/R/tests/testthat", reporter="summary",
                              stop_on_failure=FALSE, load_package="installed", package="SAShiny")
data <- as.data.frame(result)
summary <- data[vapply(data,is.atomic,logical(1))]
jsonlite::write_json(summary, "/tmp/audit/results/testthat.json",
                     auto_unbox=TRUE, pretty=TRUE)
if (sum(data$failed)>0L || any(data$error)) quit(status=1)
