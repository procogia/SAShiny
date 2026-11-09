# Pre-submission builder checks for SAShiny (R).
#
# Runs the package against win-builder (devel + release), the macOS builder, and
# R-hub. These are external services: win-builder and macOS email results to the
# maintainer; R-hub needs an account/token.
#
# Run from the repository root (after `R CMD build R`):
#
#   Rscript deploy/check-builders.R
#
# Requires the `devtools` and `rhub` packages. Results are emailed to the
# maintainer (win-builder/macOS) or shown in the R-hub web UI.

# Build the tarball first.
tarball <- list.files(pattern = "^SAShiny_.*\\.tar\\.gz$", full.names = TRUE)
if (length(tarball) == 0L) {
  stop("No SAShiny tarball found. Run `R CMD build R` first.")
}
tarball <- tarball[1L]
cat("Checking", tarball, "\n")

# win-builder (devel + release) — results emailed to the maintainer.
if (requireNamespace("devtools", quietly = TRUE)) {
  cat("Submitting to win-builder (devel) ...\n")
  devtools::check_win_devel(pkg = tarball)
  cat("Submitting to win-builder (release) ...\n")
  devtools::check_win_release(pkg = tarball)
  cat("Submitting to macOS builder ...\n")
  devtools::check_mac_release(pkg = tarball)
} else {
  cat("devtools not installed; skipping win-builder/macOS. Install with:\n")
  cat("  install.packages('devtools')\n")
}

# R-hub — needs an account/token (rhub::validate_email()).
if (requireNamespace("rhub", quietly = TRUE)) {
  cat("Submitting to R-hub (check_for_cran) ...\n")
  rhub::check_for_cran(path = tarball)
} else {
  cat("rhub not installed; skipping R-hub. Install with:\n")
  cat("  install.packages('rhub')\n")
}

cat("Done. Check your email (win-builder/macOS) and the R-hub web UI.\n")