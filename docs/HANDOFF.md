# SAShiny — Handoff to new maintainers

Welcome, Shreya and Love. This document is the handoff from Mehar: the current
state, the path to CRAN/PyPI, and the rules you must follow.

## Owners

| Person | GitHub | Role |
|---|---|---|
| Mehar Pratap Singh | `meharpsingh` | author, copyright holder, CRAN maintainer (`cre`) |
| Shreya Sharma | `shreya-sharma-procogia` | contributor (`ctb`), repo collaborator |
| Love ProCogia | `love-procogia` | contributor (`ctb`), repo collaborator |
| Igor | `igor-procogia` | contributor (`ctb`), repo collaborator |
| Ahmer Khan | `ahmer-khan-0077` | contributor (`ctb`), repo collaborator |

> Note: the repo is **user-owned** (`meharpsingh/SAShiny`), so collaborators get
> `write` (not `admin`). To grant `admin`, transfer the repo to the `procogia`
> org. This is a decision for Mehar/ProCogia.

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

1. **Make the repo public** (D15) — CRAN needs a public `URL`/`BugReports`.
2. **Close #11** — run `spec/tools/live_sas_check.py` on the ProCogia VPN and
   attach the reports (see `docs/live-sas-run-sheet.md`).
3. **CRAN gaps:** ✅ vignettes, ✅ `@examples` (done). Remaining: R-hub
   (needs a validated email + token), and review the win-builder/macOS results
   (submitted 2026-11-09; results emailed to `meharpsingh@gmail.com`).
4. **PyPI gaps:** ✅ Trusted Publishing workflow, ✅ TestPyPI rehearsal script
   (`deploy/testpypi-rehearsal.sh`). Remaining: run it with a TestPyPI token.
5. Submit CRAN → PyPI.

## Builder / rehearsal status (2026-11-09)

- **win-builder (devel + release)** — submitted; results emailed to
  `meharpsingh@gmail.com`.
- **macOS builder** — submitted; results at
  `https://mac.R-project.org/macbuilder/results/1794281604-3cacade0f652cbc5/`.
- **R-hub** — blocked: needs a validated email (`rhub::validate_email()`) and the
  repo to be public (or a GitHub token). Command: `rhub::rhub_check()`.
- **TestPyPI** — blocked: needs a TestPyPI token. Command:
  `cd Python && uv publish --publish-url https://test.pypi.org/legacy/ --token <token>`.

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
git clone https://github.com/meharpsingh/SAShiny.git
cd SAShiny
# R
R CMD build R && R CMD check --as-cran SAShiny_*.tar.gz
# Python
cd Python && uv sync && uv run pytest
```