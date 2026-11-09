# Local SAS test for SAShiny (manual, opt-in — NOT part of the package checks).
#
# Installs the built R package locally and runs the three example contracts
# against a locally-running SAS 9.4 via the saspy engine. This is a separate,
# manual validation that leverages SAS on this machine; it is outside the
# package's automated checks (which use the mock engine).
#
# Prerequisites:
#   1. Build the package: `R CMD build R` (produces SAShiny_0.1.0.tar.gz).
#   2. A local SAS 9.4 workspace server (IOM) or SSH, with credentials in
#      `~/.authinfo` (keyed by `iom`).
#   3. `reticulate` + `saspy` installed (Python).
#
# Run from the repository root:
#
#   Rscript deploy/local-sas-test.R --host <sas-host> --port 8591
#
# Or for SSH:
#
#   Rscript deploy/local-sas-test.R --host <sas-host> --saspath /path/to/sas_u8

args <- commandArgs(trailingOnly = TRUE)
host <- NULL
port <- 8591L
saspath <- NULL
i <- 1L
while (i <= length(args)) {
  if (args[[i]] == "--host") { host <- args[[i + 1L]]; i <- i + 2L }
  else if (args[[i]] == "--port") { port <- as.integer(args[[i + 1L]]); i <- i + 2L }
  else if (args[[i]] == "--saspath") { saspath <- args[[i + 1L]]; i <- i + 2L }
  else { i <- i + 1L }
}

if (is.null(host)) {
  stop("--host is required (the local SAS 9.4 host).")
}

# Install the package locally.
tarball <- list.files(pattern = "^SAShiny_.*\\.tar\\.gz$", full.names = TRUE)
if (length(tarball) == 0L) {
  stop("No SAShiny tarball found. Run `R CMD build R` first.")
}
install.packages(tarball[1L], repos = NULL, type = "source")
library(SAShiny)

# Connect to local SAS 9.4.
engine <- sas_connect("sas94", host = host, port = port, saspath = saspath)

# Run the three example contracts with their default inputs.
examples <- list(
  general = "examples/general/cars_explorer.sashiny.yml",
  pharma = "examples/pharma/ae_summary.sashiny.yml",
  aml = "examples/aml/cash_aggregation_tuning.sashiny.yml"
)

for (name in names(examples)) {
  path <- examples[[name]]
  if (!file.exists(path)) {
    cat(sprintf("SKIP %s: %s not found\n", name, path))
    next
  }
  contract <- sas_contract(path)
  # Use the contract's default inputs.
  values <- list()
  for (iid in names(contract$data$inputs %||% list())) {
    spec <- contract$data$inputs[[iid]]
    if (!is.null(spec$default) && spec$type != "dataset") {
      values[[iid]] <- spec$default
    }
  }
  result <- sas_run(contract, values, engine)
  cat(sprintf("%-8s -> %s\n", name, result$status))
}

cat("Done.\n")