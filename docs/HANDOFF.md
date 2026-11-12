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

## Current state (0.1.0, Beta)

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
- **Quality:** `R CMD check` 0 errors/warnings; Python 122 tests + ruff/mypy
  clean + 90% coverage.

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

## Path to CRAN / PyPI (remaining work)

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
- **Next:** CRAN reviewers reply to `meharpsingh@gmail.com`. Answer within
  the time they set, fix anything they raise, and resubmit with a bumped
  version (`0.1.3`) and an updated `NEWS.md`. Do not reply from a different
  address, and do not resubmit the same version number.
- PyPI / TestPyPI: both pending publishers are configured. `sashiny` 0.1.1,
  0.1.2 and 0.1.3 are on real PyPI. 0.1.2 had a chart-backend bug (plotnine
  received the raw dict instead of a DataFrame), found by a Daytona smoke test
  on 2026-11-12; 0.1.3 (the fix, from #18/#20/#21) is published and supersedes
  it. Verified: `sashiny==0.1.3` installs from PyPI and renders charts with
  matplotlib/plotnine/plotly.
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