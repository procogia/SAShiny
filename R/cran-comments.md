## Submission

This is a resubmission of SAShiny (previous version 0.1.6, a new submission
that was pending manual inspection). Version 0.2.0 narrows the package's scope
and adds publishing to Posit Connect; see NEWS.md.

## Test environments

* Windows 11, R 4.6.1: `R CMD check --as-cran`.
* GitHub Actions: ubuntu (R devel, release, oldrel-1, 4.1), macOS (release) and
  Windows (release).
* win-builder (R-devel) and the macOS builder (R-release) before submission.

## R CMD check results

0 errors | 0 warnings | 1 note

* New submission.
* "Possibly misspelled words in DESCRIPTION: PBC" may appear. It is the
  correct legal suffix in 'Posit Software, PBC', used in the trademark
  statement.

## Downstream dependencies

There are currently no downstream dependencies for this package.

## Notes for the CRAN reviewers

These notes explain the design choices that are most likely to raise
questions during review.

1. **'SAS' is commercial software and is never needed for checks.** The
   package runs 'SAS' programs only on a live, licensed 'SAS' 9.4, 'SAS Viya'
   or 'SAS OnDemand for Academics' system, reached through the Python package
   'saspy' via 'reticulate' (both optional, in Suggests or
   SystemRequirements). Installing the package, running examples, building
   the vignette and running the tests need no 'SAS', no Python, no Java and no
   internet access.

2. **Licence responsibility is the user's, and is acknowledged explicitly.**
   The package cannot verify a 'SAS' licence. A run on a live engine returns
   an error result unless the user sets `license_ack = TRUE`,
   `options(SAShiny.license_ack = TRUE)` or the environment variable
   `SASHINY_LICENSE_ACK=true`. Without an acknowledgement nothing is sent to
   'SAS' (see `?sas_connect`, section "Licence responsibility"). The package
   never sets the option itself. It does not print startup messages.

3. **How the tests work without 'SAS'.** `tests/testthat` uses two internal
   fixtures: a fake saspy session (`helper-fakesas.R`) and an offline mock
   engine that replays hand-written results (`R/engine-mock.R`). Neither is
   exported. Both refuse to run unless `TESTTHAT=true`, so users cannot feed
   logs or results that did not come from 'SAS' into an app. Tests that need
   a live 'SAS' system skip unless `SASHINY_LIVE=1`. Tests that start a
   background R process, or that need 'shiny', call `skip_on_cran()` and
   `skip_if_not_installed()`.

4. **Examples.** Every example that runs during checks completes in well under
   five seconds and needs no 'SAS' or network: it builds configurations,
   validates the bundled `inst/examples/minimal` contract, or shows the
   licence-acknowledgement error. Examples that would connect to 'SAS' or
   Posit Connect, or open an interactive gadget, are wrapped in `\dontrun{}`.
   They cannot run without external commercial systems and credentials, and
   the comment above each one says so.

5. **No side effects on the user's system.**
   * Files are written only under `tempdir()` (a temporary saspy
     configuration and background-run results), and removed on close.
   * `sas_program_server()` raises `shiny.maxRequestSize` to the contract's
     declared upload limit and restores the previous value when the Shiny
     session ends. `sas_publish()` sets `SASHINY_LICENSE_ACK` only for the
     duration of the deploy call and restores it with `on.exit()`. The test
     suite uses `withr::local_envvar()`/`local_options()`.
   * `.sashiny_find_java()` and `.sashiny_find_ssh()` only look up paths
     with `Sys.which()`. They run nothing.
   * Background R processes ('callr') start only for a live 'SAS' run inside
     a running Shiny app. They are supervised and killed on timeout or when
     the browser session ends.

6. **Network access** happens only in `sas_publish()`/`sas_publish_addin()`
   (through 'rsconnect') and when a live 'SAS' session is opened. Neither
   runs during checks. The publish tests replace the 'rsconnect' functions
   with stubs (`testthat::local_mocked_bindings()`).

7. **Credentials** are never function arguments, never written to files and
   never bundled. They come from `~/.authinfo` or environment variables.
   `sas_publish()` always excludes credential files (`.authinfo`, `.Renviron`,
   `.env`, `*.pem`, `*.key`) from the bundle.

8. **Trademarks.** 'SAS' is a registered trademark of SAS Institute Inc. and
   'Shiny' and 'Posit Connect' are trademarks of Posit Software, PBC. This
   package is not affiliated with or endorsed by either company. Software
   names are in single quotes in DESCRIPTION.

9. Code comments starting with `CRAN:` mark the places discussed above.
