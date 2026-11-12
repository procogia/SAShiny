# Forecasting: ARIMA / SARIMA model explorer

A fictional pharmaceutical company forecasts monthly prescription demand for three
products in three regions, to plan inventory and production. The SAS program fits a
curated set of ARIMA and seasonal ARIMA models with `PROC ARIMA` (SAS/ETS), compares
them on a holdout window, refits the chosen model on all months and forecasts ahead
with prediction intervals.

The workflow in the app is: **explore the data → compare models → choose the final
model → forecast.**

## Files

| File | Purpose |
|---|---|
| [`arima_forecast.sas`](arima_forecast.sas) | The SAS program: a macro library with `%arima_forecast(...)` |
| [`arima_forecast.sashiny.yml`](arima_forecast.sashiny.yml) | The SAShiny contract: inputs, outputs and labels |
| [`data/generate_rx_data.py`](data/generate_rx_data.py) | Standalone generator for the simulated data (Python standard library only) |
| [`data/demo_rx_monthly.csv`](data/demo_rx_monthly.csv) | The sample file: 1,080 rows, seed 42 |

SAShiny itself submits the program, uploads the data and returns the results, so the
example needs no separate Python runner.

## Data

One row per month, product and region. The sample has 120 months (January 2016 to
December 2025) for 9 series (Drug A, B, C × West, Central, East).

| Column | Description |
|---|---|
| `month` | First day of the month, `YYYY-MM-01` |
| `product` | `Drug A`, `Drug B` or `Drug C` |
| `region` | `West`, `Central` or `East` |
| `prescriptions` | Monthly prescriptions, the forecasting target |
| `shock_flag` | 1 in months with a simulated disruption or spike (optional in your own file) |
| `scenario` | The simulated demand pattern (not used by the program) |

Each series combines a demand level with a trend and a small random drift, annual
seasonality whose monthly factors change slightly from year to year, autocorrelated
noise and occasional shocks. In the default `mixed` file each product has its own
scenario:

| Product | Scenario | Pattern |
|---|---|---|
| Drug A | `standard` | Growing demand, mild seasonality |
| Drug B | `seasonal` | Strong winter peak, suited to SARIMA |
| Drug C | `disruption` | Declining demand with several supply drops and spikes |

Regenerate the sample, or make another scenario or seed:

```sh
python examples/forecasting/data/generate_rx_data.py
python examples/forecasting/data/generate_rx_data.py --scenario seasonal --seed 7 --out my_rx.csv
```

The same seed always gives an identical file. CI checks that the committed sample
matches the generator.

In the app, **Use the sample file** is ticked by default, and the **Input data (CSV)**
download returns the data the run used. You can upload your own CSV, xlsx, xpt or
sas7bdat file with the same columns and product and region names. Missing months are
allowed: the run reports them as a warning and `PROC ARIMA` treats them as missing
values.

## What the program does

1. **Data.** Selects the product, region and months, sums duplicate rows per month,
   fills the monthly grid, and optionally takes logs. It stops with a clear `ERROR`
   when the series is too short (fewer than holdout + 36 months), or when the log
   transform meets zero or negative values.
2. **Candidates.** Fits eight models on the training months (all but the last
   *holdout* months):

   | Id | Model |
   |---|---|
   | M1 | ARIMA(1,1,0) |
   | M2 | ARIMA(0,1,1) |
   | M3 | ARIMA(1,1,1) |
   | M4 | SARIMA(0,1,1)(0,1,1)[12] (the "airline" model) |
   | M5 | SARIMA(1,1,0)(0,1,1)[12] |
   | M6 | SARIMA(1,1,1)(0,1,1)[12] |
   | M7 | SARIMA(1,0,0)(0,1,1)[12] with a constant |
   | M8 | SARIMA(2,1,0)(1,1,0)[12] |

   With **Final model: Manual**, your own orders (p, q 0–2; d, P, D, Q 0–1; period
   12) are fitted as a ninth candidate. Models with regular differencing (d = 1)
   have no constant. Models without it keep one: the mean, or, with seasonal
   differencing only (M7), the average change from one year to the next.
3. **Evaluation.** Forecasts the holdout months with each candidate and scores them
   by RMSE, MAE and WAPE on the prescription scale. AIC and SBC from the training fit
   are also shown, but they compare models with the same differencing only. Each
   candidate's log goes to a temporary file. A candidate that fails or does not
   converge is marked **Not converged** and left out of automatic selection, and its
   messages are copied into the log as notes. A failed candidate therefore never
   fails the run.
4. **Selection.** **Automatic** picks the usable candidate with the lowest holdout
   score for the chosen metric. You can override it with Manual or any of M1–M8.
   If only the manual model converges, it becomes the recommendation (with a
   warning).
5. **Final fit and forecast.** Refits the final model on all months and forecasts
   3–12 months ahead at the chosen interval level. Log forecasts are
   back-transformed with the usual variance correction.
6. **Diagnostics.** Parameter estimates, the Ljung-Box white-noise test, residuals
   over time, residual ACF and a residual histogram.

## Outputs in the app

| Section | Output |
|---|---|
| Run summary | Status, months used, candidates fitted and usable, recommended and final model, Ljung-Box p (the elapsed time is a note in the SAS log) |
| Data | History with moving average and shock months; the series table |
| Explore | Seasonal profile by calendar month; ACF and PACF after the final model's differencing |
| Evaluation | Candidate table with ranks and decisions; holdout score chart; holdout forecasts versus actual |
| Model | Final model parameter estimates |
| Diagnostics | Ljung-Box table; residual, residual ACF and residual histogram charts |
| Forecast | History, fitted values, forecast and prediction interval; the forecast table |
| Downloads | Forecast, model comparison, fitted values and residuals, input data (CSV) |

The program leaves these datasets in `WORK`: `RUN_STATUS`, `SERIES`,
`MODEL_COMPARISON`, `ESTIMATES`, `WHITE_NOISE`, `DIAGNOSTICS` and `FORECAST`. Its nine
graphs always come in the order listed in its header, which is how the contract's
`select:` numbers find them.

## Running it

**In the demo app.** Open the **Forecasting** tab, choose a live SAS connection in the
sidebar and press **Build and compare models**. A run takes a few seconds on SAS
OnDemand for Academics.

**In SAS Studio, without SAShiny.** Import the CSV as `WORK.RX_MONTHLY` (with `MONTH`
as a SAS date), then:

```sas
%include "arima_forecast.sas";
%arima_forecast(product='Drug B', region='West', final_model=best, horizon=6);
```

The program needs SAS/ETS (`PROC ARIMA`, `PROC EXPAND`), which SAS OnDemand for
Academics, SAS 9.4 with SAS/ETS and SAS Viya all provide.

## Scope of this first version

Included: simulated data with a download, custom file upload, ARIMA and seasonal
ARIMA, manual orders, automatic candidate comparison, holdout validation, residual
diagnostics, forecast charts and CSV exports.

Possible later extensions: rolling-origin cross-validation, ARIMAX with external
regressors, forecasting every product and region in one run, and intervention models
for outliers.

The contract format gives every SAShiny program one sidebar and a column of output
cards. The section names (Data, Explore, Evaluation, Model, Diagnostics, Forecast) are
therefore prefixes on the card titles, not separate sub-tabs.

## Licensing note

SAS OnDemand for Academics is licensed to one user for learning, teaching and
non-commercial academic work. Use it to develop and test this example. A demo that
other people run needs a SAS environment licensed for that use. The program and
contract do not depend on the connection, so moving to another SAS server only
changes the app's connection settings.
