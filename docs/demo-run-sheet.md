# Lisbon demo — run-sheet

The demo shows the **same unchanged SAS programs** driving a Shiny app in **R and
Python side by side**, across three tracks (General / Pharma / AML). This run-sheet
is the presentation script plus the fallback plan.

> **Date:** 2026-11-11. **Owner:** Mehar. **Primary:** local apps on Mehar's Mac
> (ProCogia VPN). **Audience:** hosted Daytona URL (Offline default).

## Before the demo (Day 3, Nov 10–11)

1. Run the live SAS check (see `docs/live-sas-run-sheet.md`) and attach the
   reports to #11.
2. Record offline results for each track so the Offline profile replays them:
   - Start either demo app, pick a live profile, and press Run on each tab with
     the inputs you will show. Live runs are saved to `examples/recordings/`
     automatically (spec §8.3); recordings from R and Python are
     interchangeable.
   - Recordings match exact input values. If you change an input during the
     demo, record that combination too, or the Offline profile shows
     "no recording matches these inputs".
   - Commit the recordings (synthetic example data only).
3. Start the local apps:
   - R: `shiny::runApp("R/inst/examples/demo")`
   - Python: `cd Python && uv run --with shiny python examples/demo/app.py`
4. Confirm the Daytona hosted URL is up (see #12) and defaults to Offline.

## The demo (3 tracks × 2 languages)

For each track, show the **same SAS program** (`examples/<track>/*.sas`) driving
both apps:

| Track | SAS program | Inputs to show | Outputs to show |
|---|---|---|---|
| General | `cars_explorer.sas` | origin, type, min MSRP | summary table, 2 plots, HTML, CSV/PDF |
| Pharma | `ae_summary.sas` (macro) | ADSL/ADAE upload, arms, SAFFL, date window, min % | TEAE table, plot, RTF/XPT |
| AML | `cash_aggregation_tuning.sas` | transactions upload, segments, threshold, look-back, period | sensitivity table, alerts, XLSX/CSV |

**Talking points per track:**
- The `.sas` file is **byte-for-byte unchanged** — show the sidecar YAML, not a
  rewritten program.
- Inputs are validated (V001–V014) and injected only through the safe quoting
  scheme (§6.3); show the generated wrapper's `call symputx` + `%superq`.
- The run metadata panel shows `run_id`, contract/program hashes, rendered
  macros, timestamps, engine/SAS version, and status — the audit trail.

## Connection profiles

- **Local (Mehar's Mac, VPN):** ProCogia Viya, ProCogia 9.4 (IOM/SSH), ODA,
  Offline.
- **Hosted (Daytona):** ODA (only if the tier allows TCP 8591) and Offline
  (default).

Show the profile picker and the live/offline toggle; switch profiles live to
demonstrate the same app on different backends.

## Fallback plan

| Risk | Mitigation |
|---|---|
| VPN drops in the venue | Switch the profile to ODA or Offline in the app; recordings were made the day before. |
| Daytona Tier 1/2 blocks outbound non-HTTP | Hosted app defaults to Offline; verify the tier early (see #12). |
| ODA account not created | Skip ODA; the demo uses Offline recordings. |
| Live SAS slow/unavailable | Offline recordings replay instantly; the mock engine is the default. |

## After the demo

- Tag the pre-release `v0.0.1-demo` from the same code that continues to release.
- Note any issues found during the dry-run in GitHub issues.