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
- **Phase 3 (saspy engine + pool)** implemented: saspy engine, connection
  selection (ODA/Viya/SAS 9.4), bounded pool. **Live SAS is unverified (#11).**
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
uv run --no-project --with jsonschema --with pyyaml python spec/tools/check_spec.py
# R
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python
cd Python && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest
```

## Path to CRAN / PyPI (remaining work)

1. ~~Make the repo public (D15)~~ — done: <https://github.com/procogia/SAShiny>.
2. **Close #11** — run `spec/tools/live_sas_check.py` on the ProCogia VPN and
   attach the reports (see `docs/live-sas-run-sheet.md`).
3. **CRAN gaps:** vignettes, examples, R-hub and the macOS builder are clean.
   Remaining: review the three win-builder replies emailed to
   `meharpsingh@gmail.com`.
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
- **win-builder (devel, release, oldrelease)** - resubmitted after the repo went
  public. Results are emailed to `meharpsingh@gmail.com`. **Not yet reviewed**:
  Mehar must read the three replies and send any NOTE/WARNING/ERROR to the team.
- **GitHub macOS CI** - the runner queue has been unreliable; R-hub macOS and the
  macOS builder both pass.
- **PyPI / TestPyPI** - see [pypi-trusted-publishing.md](pypi-trusted-publishing.md).
  Use owner `procogia` (not `meharpsingh`). Both names are free.
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