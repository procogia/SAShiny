# Demo recording checklist (Lisbon, 2026-11-11)

Record each track once against live SAS so the Offline profile can replay it.
Recordings are shared between R and Python, so record in one app only.

Faster: run the live test suite with `SASHINY_RECORD_TO` set. It records and
checks all six scenarios below in one go (`docs/live-demo-tests.md`). The
scenarios themselves are defined in `examples/demo-scenarios.yml`.

## Before you start

- [ ] Live check is green for the profile you will use (`spec/tools/live_sas_check.py`, issue #11).
- [ ] `~/.authinfo` holds the credentials; the connection variable is set (`SASHINY_ODA_REGION`, `SASHINY_VIYA_URL` or `SASHINY_SAS94_HOST`).
- [ ] VPN is on if you use ProCogia Viya or SAS 9.4.
- [ ] Start one demo app from the repository root:
      `cd Python && uv run --extra shiny --extra saspy --extra upload shiny run examples/demo/app.py`
- [ ] In the sidebar, set **SAS connection** to the live profile (not Offline).

## Rules that keep recordings matching

- A recording replays only for the **exact same inputs**, so press Run with the values below and nothing else.
- Leave **Use the sample file** ticked. Uploading any other file, even one with the same contents but different bytes, gives a different recording.
- Multi-select boxes (the **Vehicle type** dropdown) record values **in the order you pick them**. Leave the defaults alone, or pick them in the same order during the demo.
- Do not edit the `.sas` or `.sashiny.yml` files after recording. Any byte change in the contract makes every recording for it stop matching.

## Track 1: General (`cars_explorer`)

- [ ] Origin: Asia, Europe, USA (default)
- [ ] Vehicle type: Sedan, SUV, Sports, Truck, Wagon (default)
- [ ] Minimum MSRP: 20000 (default)
- [ ] Press **Summarise**; the Run card shows `status: success` with no `collect error` lines
- [ ] Cards show: summary table, 2 plots, full SAS output, log; CSV and PDF downloads open

## Track 2: Pharma (`ae_summary`)

- [ ] ADSL and ADAE: **Use the sample file** ticked for both
- [ ] Actual treatment: all three arms (default)
- [ ] Safety population flag: SAFFL = Y (default)
- [ ] AE start date window: 2025-01-01 to 2025-12-31 (default)
- [ ] Minimum incidence: 5 (default)
- [ ] Press **Build safety tables**; `status: success`, no `collect error` lines
- [ ] Cards show: AE plot, AE table, demographics table, report, log; RTF and XPT downloads open

## Track 3: AML (`cash_aggregation_tuning`)

- [ ] Transactions: **Use the sample file** ticked
- [ ] Customer segments: Retail, SME, Corporate (default)
- [ ] Alert threshold: 10000 (default)
- [ ] Look-back window: 30 (default)
- [ ] Transaction dates: 2026-01-01 to 2026-06-30 (default)
- [ ] Press **Run scenario**; `status: success`, no `collect error` lines
- [ ] Cards show: ATL/BTL plot, ATL/BTL table, alerts table, log; XLSX and CSV downloads open

## Optional: a second scenario per track

To change one input on stage, record that exact combination too, for example:

- [ ] General: Minimum MSRP 40000
- [ ] Pharma: Minimum incidence 10
- [ ] AML: Alert threshold 25000

## Verify and commit

- [ ] `examples/recordings/` has one new `.json` file per Run (3, or 6 with the optional scenarios)
- [ ] `SASHINY_REQUIRE_RECORDINGS=1` passes in both languages (`docs/live-demo-tests.md`)
- [ ] Switch the profile to **Offline**, press Run on each tab, and check the Run card reads `offline: replayed recording from ...`
- [ ] Check the same in the R app (`Rscript -e 'shiny::runApp("R/inst/examples/demo")'`)
- [ ] Turn off the VPN and repeat one track to confirm the fallback works without a network connection
- [ ] Commit: `git add examples/recordings/*.json && git commit -m "Record demo runs"` and push, so the Daytona URL serves them too
