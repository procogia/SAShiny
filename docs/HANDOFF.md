# SAShiny — Handoff to new maintainers

Welcome, Shreya, Love, Igor and Ahmer. This document is the handoff from Mehar:
the current state, the path to CRAN/PyPI, and the rules you must follow.

## Owners

| Person | GitHub | Role |
|---|---|---|
| Mehar Pratap Singh | `meharpsingh` | author, copyright holder, CRAN maintainer (`cre`) |
| Shreya Sharma | `shreya-sharma-procogia` | contributor (`ctb`), repo collaborator |
| Love ProCogia | `love-procogia` | contributor (`ctb`), repo collaborator |
| Igor | `igor-procogia` | contributor (`ctb`), repo collaborator |
| Ahmer Khan | `ahmer-khan-0077` | contributor (`ctb`), repo collaborator |

> Note: the repo lives at **procogia/SAShiny** and is public. It was transferred
> from `meharpsingh/SAShiny` on 2026-11-10 (the old URL redirects). The four new
> owners have `admin`. Secret scanning and push protection are enabled.

## Current state (R 0.1.6, Python 0.1.7, Beta)

- **Phase 2 (core)** done: contract loader/validator, value renderer, wrapper
  generator, lint, mock engine, result object — both R and Python pass every
  fixture (97/97 spec check).
- **Phase 3 (saspy engine + pool)** implemented in R and Python: saspy session
  from generated config, uploads (§7), full result collection (§8.2),
  `choices_from` (§6.4), recordings shared across languages (§8.3), pools with
  one SAS session per pooled session. Tested against a fake saspy session in
  both languages. **Live SAS is unverified (#11)** and `examples/recordings/`
  is empty until someone records the demo inputs against live SAS.
- **Phase 4 (Shiny modules)** done: auto-UI, custom override, log panel,
  downloads, multi-program app, Shiny test client.
- **Quality:** `R CMD check --as-cran` Status OK (Debian, R 4.5.x, 2026-11-14);
  Python 312 tests pass (37 skipped) and ruff/mypy are clean; the spec check passes 152/152.
- **Published:** PyPI `sashiny` 0.1.7 (release `py-v0.1.7`). CRAN: 0.1.1 is in
  the incoming queue; the 0.1.6 tarball is prepared, but the maintainer has not
  submitted it yet.

## Non-negotiable rules (from `.github/copilot-instructions.md`)

1. **Spec first** — `spec/CONTRACT.md` is the source of truth; a behaviour change
   starts there and in its fixtures, then R and Python follow.
2. **Never modify a user's SAS program** — submit it verbatim (§6.3).
3. **Security** — user values reach SAS only as single-quoted `call symputx`
   literals, then `%superq`. Never interpolate user text any other way.
4. **Byte-exact wrapper** — generated SAS must match the fixtures exactly.
5. **No SAS in automated checks** — CRAN/PyPI/CI use the mock engine; live SAS is
   opt-in (`SASHINY_LIVE=1`).
6. **R/Python parity** — implement every feature in both, or open an issue.
7. **No credentials** in code/contracts/tests — they come from `~/.authinfo` or
   the platform secret store.

## Gates before every PR

```sh
# spec check
uv run --no-project --python 3.12 --with jsonschema --with pyyaml python spec/tools/check_spec.py
# R
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python
cd Python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

## Release checklist (lockstep versions, spec section 11)

The R package and the Python library always ship the same version.

1. Bump `R/DESCRIPTION` `Version:` and `Python/src/sashiny/__init__.py` `__version__` to the same value.
2. If the spec, schema or fixtures changed since the last release, bump the minor part of
   "Spec release" in `spec/CONTRACT.md` and set the same value in `R/R/info.R`
   (`.sashiny_spec_release`) and `Python/src/sashiny/info.py` (`SPEC_RELEASE`).
3. Run `python spec/tools/check_versions.py` (CI runs it in the `spec` workflow) and all three gates.
4. Move the NEWS.md / CHANGELOG.md entries under the new version heading; update `R/cran-comments.md`.
5. Tag both: `r-v<version>` and `py-v<version>`. Publish TestPyPI, then PyPI (Trusted Publishing).
6. Submit to CRAN unless an earlier submission is still within CRAN's update interval; then queue it
   and note the queued version here.



1. ~~Make the repo public (D15)~~ — done: <https://github.com/procogia/SAShiny>.
2. **Close #11** — run `spec/tools/live_sas_check.py` on the ProCogia VPN and
   attach the reports (see `docs/live-sas-run-sheet.md`).
3. **CRAN gaps:** vignettes, examples, R-hub, macOS builder, win-builder release
   and oldrelease are clean. Open: win-builder R-devel shows an ERROR (see below).
4. **PyPI gaps:** the Trusted Publishing workflow supports TestPyPI and PyPI.
   Configure pending publishers in the respective web UIs, then run the
   TestPyPI workflow. A long-lived token is not required.
5. Submit CRAN → PyPI only after the external results and public URLs are clean.

## Builder / rehearsal status (2026-11-10)

- **macOS builder** - **Status: OK**, 0 errors, 0 warnings, 0 notes, including
  the PDF manual, once the repo was public:
  <https://mac.R-project.org/macbuilder/results/1794325540-ff26684d316762fb/>.
  Earlier failures were the service's dependency cache, not the package.
- **R-hub** - Linux, Windows, macOS, `clang-asan` and `nosuggests` all
  `Status: OK` (run 42839082918). The `donttest` platform fails before
  checking SAShiny, because R-hub's own `processx.so` lacks an ASAN symbol.
- **Local** - `R CMD check --as-cran`: the only NOTE is "New submission".
  `urlchecker` reports all URLs correct.
- **win-builder, commit ab2a748 (read from Gmail on 2026-11-10)**:
  R 4.6.2 release `Status: 1 NOTE`; R 4.5.3 oldrelease `Status: 1 NOTE`;
  **R-devel `Status: 1 ERROR, 1 NOTE`**. The NOTE is "New submission" plus
  "Possibly misspelled words: PBC" (from the 'Posit Software, PBC' trademark
  text, which is correct as written). The R-devel ERROR is
  `Files named as vignettes but with no recognized vignette engine:
  'inst/doc/getting-started.Rmd'`. Our tarball contains no `.Rmd` at all (the
  vignette is `.Rhtml`). R-devel passed at 06:05 PT, then failed on every run
  from 07:04 PT with tarball contents that pass on release, oldrelease, R-hub
  Windows R-devel and the macOS builder. A fourth R-devel run was submitted at
  09:24 PT and had not replied after 22 minutes. Treat R-devel as unresolved.
  **Do not submit to CRAN while R-devel shows an ERROR.**
- **GitHub macOS CI** - the runner queue has been unreliable; R-hub macOS and the
  macOS builder both pass.
- **PyPI / TestPyPI** - see [pypi-trusted-publishing.md](pypi-trusted-publishing.md).
  Use owner `procogia` (not `meharpsingh`). Both names are free.
- **TestPyPI** - the pending publisher is configured and the publish workflow
  succeeds. `sashiny` 0.1.0 and 0.1.1 are on TestPyPI. 0.1.1 fixes the core
  import so `import sashiny` works without the optional `shiny` extra.
## Release 0.3.1 (2026-11-20)

- Tags `r-v0.3.1` and `py-v0.3.1` on `main`; GitHub releases created for both.
- **PyPI:** `sashiny` 0.3.1 published through Trusted Publishing (after a TestPyPI rehearsal).
- **CRAN: queued.** 0.2.0 is still inside CRAN's update interval. Submit `SAShiny_0.3.1.tar.gz`
  (built from `r-v0.3.1`, `R CMD check --as-cran` 1 NOTE for HTML Tidy locally) once that window
  ends. `R/cran-comments.md` already explains the new Imports `callr`, `cli` and `lifecycle`.
- Live SAS acceptance for the 0.3.1 features is tracked in `docs/qa-live-checklist.md`
  (Igor and Shreya, ten checks each).

## CRAN submission (2026-11-10)

- **Submitted** SAShiny 0.1.0 (source commit `cf65c09`) through
  <https://cran.r-project.org/submit.html> at 10:5x PT as Mehar Pratap Singh
  (`meharpsingh@gmail.com`), and **confirmed** via the emailed link. CRAN's
  "The following package was uploaded to CRAN" message arrived at 11:03 PT.
- **Resubmitted** SAShiny 0.1.1 (source commit `04974ca`) at 19:3x PT and
  **confirmed** via the emailed link. CRAN's "uploaded to CRAN" message arrived
  at 19:48 PT. 0.1.1 supersedes 0.1.0 and adds the `%superq` WHERE-clause fix
  (issue #16), the ODA session-setup fix (PR #15), and the live dataset-upload /
  empty-table fixes (issue #17).
- The 0.1.0 submission was auto-processed and was "pending a manual inspection"
  (CRAN email 12:32 PT); the 0.1.1 resubmission replaces it.
- **Prepared** SAShiny 0.1.2 to supersede 0.1.1. As of 2026-11-12 CRAN's
  incoming queue holds only 0.1.1 (`newbies`), so 0.1.2 has not been received;
  submit it from `main` after the chart-backend fixes (#18, #20, #21) are
  merged. 0.1.2 adds the client-side `chart` output type (spec §8.5): SAS produces only
  the data, and the Shiny module renders the plot client-side via a declarative
  `spec` or a per-language `render` callback (ggplot2 / base / plotly in R;
  plotnine / matplotlib / plotly in Python).
- **Prepared** SAShiny 0.1.4 (source commit `1a1e9b7`) to supersede 0.1.1.
  0.1.4 adds the chart-backend fixes (#18, #20, #21), the XPT v8 demo-checker
  fix (#25), the Shiny module card-layout fix (#26) and the Forecasting demo
  track (PR #27). `R CMD check --as-cran` is clean (0 errors, 0 warnings,
  1 NOTE "New submission"). The tarball is `SAShiny_0.1.4.tar.gz`; submit it
  via <https://cran.r-project.org/submit.html> (web form, maintainer email
  `meharpsingh@gmail.com`).
- **Next:** CRAN reviewers reply to `meharpsingh@gmail.com`. Answer within
  the time they set, fix anything they raise, and resubmit with a bumped
  version (`0.1.5`) and an updated `NEWS.md`. Do not reply from a different
  address, and do not resubmit the same version number.
- PyPI / TestPyPI: both pending publishers are configured. `sashiny` 0.1.1
  through 0.1.5 are on real PyPI. 0.1.2 had a chart-backend bug (plotnine
  received the raw dict instead of a DataFrame), found by a Daytona smoke test
  on 2026-11-12; 0.1.3 (the fix, from #18/#20/#21) supersedes it, 0.1.4 (the
  Shiny module card-layout fix, #26) supersedes 0.1.3, and 0.1.5 (the
  Forecasting demo track, PR #27) supersedes 0.1.4. Verified: `sashiny==0.1.5`
  installs from PyPI.
## Open issues

- #11 — Live SAS check reports (blocked on VPN + `~/.authinfo`).
- #12 — Demo hosting on Daytona (tier verified: ODA reachable; see
  `deploy/daytona/`).

## Local SAS test (outside the package)

`deploy/local-sas-test.R` installs the package locally and runs the three
examples against a local SAS 9.4. It is manual/opt-in, not part of the package
checks. See the script header for usage.

## Getting started

```sh
git clone https://github.com/procogia/SAShiny.git
cd SAShiny
# R
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python
cd Python && uv sync && uv run pytest
```