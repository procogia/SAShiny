# SAShiny demo — run-sheet

The demo shows the **same unchanged SAS programs** driving a Shiny app in **R and
Python side by side**, across three tracks (General / Pharma / AML). This run-sheet
is the presentation script plus the fallback plan.

> **Owner:** Mehar. **Primary:** local apps on Mehar's Mac (ProCogia VPN).
> **Audience:** hosted Daytona URL (ODA default).

## Local setup (once)

1. Connect the ProCogia VPN for the Viya and 9.4 profiles.
2. Obtain access to a compatible SAS compiler for the selected profile; SAShiny
   does not provide SAS. Install Java (for SAS IOM) and the project dependencies. Python needs the
   `shiny`, `saspy` and `upload` extras; R needs the package's demo dependencies.
3. Keep credentials in `~/.authinfo` (mode `600`), never in the repository.
   The required keys are `oda`, `viya` and `iom`; see
   `docs/live-sas-run-sheet.md` for the format.
4. Set connection details for the profiles you will use:

   ```sh
   export SASHINY_ODA_REGION=us1
   export SASHINY_VIYA_URL='https://<viya-host>'
   export SASHINY_VIYA_CONTEXT="<SAS Studio compute context>"
   export SASHINY_SAS94_HOST='<sas94-host>'
   ```

   Replace the placeholders with the actual hosts and context. Omit settings
   for profiles you will not use. These are connection settings, not credentials.

## Start the local apps

Run either command from the repository root; the app's profile picker offers
SAS ODA, SAS Viya and SAS 9.4:

```sh
Rscript -e 'shiny::runApp("R/inst/examples/demo")'
```

```sh
cd Python && uv run --extra shiny --extra saspy --extra upload --extra plotnine shiny run examples/demo/app.py --host 127.0.0.1 --port 8000
```

## Before the demo

1. Confirm live SAS connectivity for the profiles you plan to demonstrate (see
   `docs/live-sas-run-sheet.md`).
2. Acknowledge the SAS licence for the system you will use
   (`SASHINY_LICENSE_ACK=true`, or `options(SAShiny.license_ack = TRUE)` in R).
   Since 0.2.0 SAShiny runs only on live, licensed SAS, so there is no offline
   fallback (spec §6.6, PLAN.md D30).
3. Run the live demo tests (`docs/live-demo-tests.md`) against each profile you
   will show.
4. Confirm the hosted Daytona sandbox is up and defaults to ODA (see
   `deploy/daytona/README.md`).

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

- **Local (Mehar's Mac, VPN):** SAS Viya, SAS 9.4 (IOM), ODA.
- **Hosted (Daytona):** ODA (default). Outbound TCP 8591 to ODA
  hosts was verified reachable from the ProCogia Daytona tier on 2026-11-14;
  details are in `deploy/daytona/README.md`.

Choose the profile with `SASHINY_PROFILE` (`oda`, `viya` or `sas94`) when you
start each app. To show the same app on different backends, start one app per
profile.

## Fallback plan

| Risk | Mitigation |
|---|---|
| VPN drops in the venue | Restart the app with `SASHINY_PROFILE=oda`. |
| Daytona ODA connection or credentials unavailable | Use the local app on VPN (Viya or SAS 9.4). |
| ODA account not created | Demo Viya or SAS 9.4 locally on VPN. |
| Live SAS slow/unavailable | Show the contract, validation and generated wrapper, which need no SAS. There is no offline replay. |

## After the demo

- Tag the pre-release `v0.0.1-demo` from the same code that continues to release.
- Note any issues found during the dry-run in GitHub issues.