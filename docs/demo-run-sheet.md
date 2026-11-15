# SAShiny demo — local run-sheet

The primary demo runs the same four unchanged SAS programs in the R and Python
Shiny apps on Mehar's Mac. Connect to the ProCogia VPN before using Viya or SAS
9.4. ODA and Offline are also available locally.

## One-time setup

- Install `uv`, R (4.1 or later), and Java 17. Java is needed for ODA and
  SAS 9.4 IOM; Offline does not need Java.
- Put credentials in `~/.authinfo` and restrict access with `chmod 600
  ~/.authinfo`. Use `oda`, `viya`, and `iom` auth keys as described in
  [`live-sas-run-sheet.md`](live-sas-run-sheet.md). Never commit credentials.
- Install the R package and its Shiny dependencies:

  ```sh
  Rscript -e 'install.packages("remotes"); remotes::install_local("R", dependencies = TRUE)'
  ```

## Start the apps

Run each command from the repository root in its own terminal. Both apps use
the same profile names and example inputs; Python listens on port 8000 and R
on port 8001.

**Python**

```sh
cd Python && uv run --extra shiny --extra saspy --extra upload \
  shiny run examples/demo/app.py --host 127.0.0.1 --port 8000
```

**R**

```sh
Rscript -e 'shiny::runApp("R/inst/examples/demo", host = "127.0.0.1", port = 8001)'
```

Open `http://127.0.0.1:8000` and `http://127.0.0.1:8001`. The profile menu
offers Offline, ODA, Viya, and SAS 9.4. Viya and SAS 9.4 require the ProCogia
VPN; live profiles need credentials and Java where they use IOM. Configure
connection details with `SASHINY_ODA_REGION`, `SASHINY_VIYA_URL`,
`SASHINY_VIYA_CONTEXT`, and `SASHINY_SAS94_HOST`.

## Offline recordings are a prerequisite

The repository currently has no committed run recordings. A fresh Offline run
therefore reports that no recording matches the inputs; building or hosting
the app does not create recordings. Before relying on Offline or publishing
the hosted image, record the synthetic demo scenarios against a live SAS
profile and commit the resulting `examples/recordings/*.json` files. Follow
[`recording-checklist.md`](recording-checklist.md), then verify the Python
scenarios with:

```sh
cd Python && SASHINY_REQUIRE_RECORDINGS=1 uv run pytest tests/test_demo_scenarios.py
```

Recordings must only contain the synthetic example data. The hosted image
defaults to Offline and includes only files present at build time.

## Hosted Daytona demo

The hosted app defaults to Offline and offers ODA only as its live profile.
The Daytona tier was verified to allow outbound TCP 8591 to ODA on
2026-11-14. Viya and SAS 9.4 remain local/VPN profiles. See
[`../deploy/daytona/README.md`](../deploy/daytona/README.md) for image build,
registry, sandbox, signed preview URL, and expiry steps.

## Walk-through

| Track | SAS program | Inputs | Outputs |
|---|---|---|---|
| General | `cars_explorer.sas` | origin, type, minimum MSRP | summary, plots, report, CSV/PDF |
| Pharma | `ae_summary.sas` | ADSL/ADAE samples, arms, SAFFL, date window, minimum incidence | tables, plot, RTF/XPT |
| AML | `cash_aggregation_tuning.sas` | transaction sample, segments, threshold, dates | sensitivity/alerts tables, XLSX/CSV |
| Forecasting | `arima_forecast.sas` | prescription sample, product, region, date window | model comparisons, charts, forecast tables |

Show that each `.sas` program is unchanged and its sidecar YAML contract
declares the inputs and outputs. Point out validation, safe macro quoting, and
the run metadata/audit panel.

## Fallback

- If the VPN is unavailable, use ODA or Offline locally.
- If live SAS is unavailable, the app attempts the matching Offline recording.
- Before presenting, confirm every scenario you intend to run has a matching
  recording; different input values require a separate recording.
