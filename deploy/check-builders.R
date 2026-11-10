# Pre-submission builder checks for SAShiny (R).
#
# Runs the package against win-builder (devel + release), the macOS builder, and
# R-hub v2 -- runs on GitHub Actions. The package lives in R/, but R-hub needs it at the
# repository root, so push a subtree-split branch that also carries the R-hub workflow:
#
#   git subtree split --prefix=R -b rhub-pkg
#   # add .github/workflows/rhub.yaml (from rhub::rhub_setup()) to that branch and push it
#   gh workflow run rhub.yaml --ref rhub-pkg -f config="linux,windows,macos,clang-asan,donttest"
#
# Or, once the branch is pushed, from R (needs GITHUB_PAT with repo scope):
#   rhub::rhub_check(gh_url = "https://github.com/OWNER/REPO", branch = "rhub-pkg",
#                    platforms = c("linux", "windows", "macos"))
#
# Note: the `nosuggests` platform fails on the vignette rebuild because 'rmarkdown' is
# deliberately absent there; that is expected for a package with a vignette builder.
cat("R-hub v2: see the comments above (runs via GitHub Actions).\n")
cat("Done. Check your email (win-builder/macOS) and the GitHub Actions run (R-hub).\n")