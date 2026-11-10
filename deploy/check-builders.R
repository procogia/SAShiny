# Pre-submission builder checks for SAShiny (R).
#
# Run from the repository root after installing `devtools`. The helpers build
# from the package directory; they do not accept an already-built tarball.

if (requireNamespace("devtools", quietly = TRUE)) {
  cat("Submitting to win-builder (devel and release) ...\n")
  devtools::check_win_devel(pkg = "R")
  devtools::check_win_release(pkg = "R")
  cat("Win-builder emails result URLs to the DESCRIPTION maintainer.\n")

  cat("Submitting to the macOS builder ...\n")
  mac_url <- devtools::check_mac_release(pkg = "R", quiet = TRUE)
  cat("macOS results:", mac_url, "\n")
} else {
  cat("Install devtools first: install.packages('devtools')\n")
}

# R-hub v2 runs on GitHub Actions. It needs DESCRIPTION at the repository root,
# whereas this monorepo keeps it in R/. Create a package-at-root helper branch
# and add .github/workflows/rhub.yaml to that branch before dispatching:
#
#   git subtree split --prefix=R -b rhub-pkg
#   gh workflow run rhub.yaml --ref rhub-pkg \
#     -f config="linux,windows,macos,clang-asan,donttest,nosuggests"
#
# Alternatively, with a GitHub PAT having repo scope:
#   rhub::rhub_check(gh_url = "https://github.com/procogia/SAShiny",
#                    branch = "rhub-pkg", platforms = c("linux", "windows", "macos"))
cat("R-hub v2: dispatch the workflow on the package-at-root rhub-pkg branch.\n")
cat("Inspect the run logs; a green job alone does not report NOTE/WARNING/ERROR counts.\n")
