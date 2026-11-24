# Survival: clinical trial explorer (Kaplan-Meier and Cox)

A fictional pharmaceutical company runs a randomized trial of an investigational drug,
**RX-101**, added to standard cancer treatment, against standard treatment alone
(**Control**). The question is:

> Does RX-101 reduce the risk of disease progression or death compared with standard
> treatment alone?

The endpoint is **progression-free survival (PFS)**: months from randomization to
progression or death, whichever comes first. Patients without an event are **censored**
at the data cutoff or when they were lost to follow-up. Handling these incomplete
time-to-event observations is what sets this demo apart from the regression and ARIMA
examples.

The SAS program uses two SAS/STAT procedures:

- `PROC LIFETEST`: Kaplan-Meier curves, median survival, number at risk, log-rank or
  Wilcoxon test.
- `PROC PHREG`: Cox proportional hazards regression, hazard ratios with confidence
  intervals, and proportional hazards diagnostics (`ASSESS PH`, Schoenfeld residuals).

The workflow in the app is: **data → Kaplan-Meier → Cox model → diagnostics → results.**
Output cards carry these words as label prefixes, so they read as sections.

## Files

| File | Purpose |
|---|---|
| [`survival_analysis.sas`](survival_analysis.sas) | The SAS program: a macro library with `%survival_analysis(...)` |
| [`survival_analysis.sashiny.yml`](survival_analysis.sashiny.yml) | The SAShiny contract: inputs, outputs and labels |
| [`survival_charts.py`](survival_charts.py), [`survival_charts.R`](survival_charts.R) | Forest-plot render callback for the SAShiny chart (plotnine / ggplot2), used by the demo apps |
| [`sas_survival_runner.py`](sas_survival_runner.py) | Runs the contract on SAS from the command line, without Shiny, and saves every output |
| [`data/generate_survival_data.py`](data/generate_survival_data.py) | Standalone generator for the simulated trial (Python standard library only) |
| [`data/adsl.csv`](data/adsl.csv), [`data/adtte.csv`](data/adtte.csv) | The sample files: 3 studies × 600 subjects, seed 42 |

SAShiny builds the sidebar and output cards from the contract, uploads the data, runs the
unchanged program and collects the results. The only extra code is the forest-plot
callback. The contract's declarative chart spec draws points, lines, bars, histograms and
boxes, but a forest plot needs confidence-interval bars, a log axis and a reference line
at HR = 1. So the demo apps pass `forest_chart` as a chart render callback (spec §8.5):
`chart_render={"forest_plot": forest_chart}` in Python, and
`render = list(forest_plot = forest_chart)` in R. Without the callback (other hosts, or
if the demo app cannot load the file, which it reports as a warning), the SAShiny view
falls back to the contract's declarative chart: the hazard ratios as points, titled as
point estimates, with the intervals in the hazard ratios table. `Python/tests/test_survival_charts.py`
and `R/tests/testthat/test-survival-charts.R` check both callbacks against the same value
and layout.

## Data

Entirely synthetic, with ADaM-like names. Regenerate the samples with:

```sh
python examples/survival/data/generate_survival_data.py
python examples/survival/data/generate_survival_data.py --scenario standard --n 300 --seed 7 --out-dir /tmp/rx
```

The same seed always gives identical files; CI checks this.

### Scenarios

Each scenario is its own study (`STUDYID`), so one pair of files holds all three and the
app's **Study** input selects one.

| Study | Scenario | True treatment effect | Purpose |
|---|---|---|---|
| `RX101-STD` | Standard trial | hazard ratio 0.70 | Moderate benefit, realistic censoring |
| `RX101-NULL` | No treatment effect | hazard ratio 1.00 | A non-significant comparison |
| `RX101-NPH` | Non-proportional hazards | 1.00 for 6 months, then 0.45 | A delayed effect that violates the Cox assumption |

Event times follow a Weibull proportional hazards model (shape 1.2) with prognostic
effects of age, sex, stage and ECOG status. Accrual is uniform over 18 months from
2023-01-02. The data cutoff is 36 months after the first randomization, so follow-up
ranges from about 18 to 36 months. Loss to follow-up is 2-4% of subjects. About 2% of
subjects have `ITTFL = N` (randomized in error).

### ADSL: one record per subject

| Variable | Type | Description |
|---|---|---|
| `STUDYID` | character | `RX101-STD`, `RX101-NULL` or `RX101-NPH` |
| `USUBJID` | character | Unique subject ID |
| `TRT01A` | character | `Control` or `RX-101` (1:1, permuted blocks of 4) |
| `AGE` | numeric | Age in years (30-85) |
| `SEX` | character | `F` or `M` |
| `STAGE` | character | Cancer stage `I`, `II` or `III` |
| `ECOG` | numeric | ECOG performance status 0-2 |
| `REGION` | character | `North America`, `Europe` or `Asia Pacific` |
| `ITTFL` | character | Intent-to-treat population flag (`Y`/`N`) |
| `RANDDT` | date | Randomization date |

### ADTTE: one PFS record per subject

| Variable | Type | Description |
|---|---|---|
| `STUDYID`, `USUBJID` | character | Link to ADSL |
| `PARAMCD`, `PARAM` | character | `PFS`, Progression-free survival (months) |
| `AVAL`, `AVALU` | numeric, character | Time to event or censoring, in `MONTHS` (days / 30.4375) |
| `CNSR` | numeric | 0 = event, 1 = censored |
| `EVNTDESC` | character | `Disease progression`, `Death`, `Study end (data cutoff)` or `Lost to follow-up` |
| `STARTDT` | date | Time origin (the randomization date) |
| `ADT` | date | Event or censoring date: `STARTDT` + days on study, never after the cutoff |

To use your own files, upload ADSL and ADTTE with these columns (the contract checks
them) and choose **Study: All studies in the files**.

## What the program does

1. **Data.** Keeps the `PFS` records, joins ADSL and ADTTE by `USUBJID`, and applies the
   study, population, arm, stage and sex filters. Records with a missing or negative
   `AVAL` or a `CNSR` other than 0/1 are dropped with a warning. Follow-up beyond the
   maximum follow-up is censored at that time. It stops with an `ERROR` if no subjects or
   no events remain.
2. **Descriptives.** Patient characteristics by arm, and events, censoring and median
   follow-up (reverse Kaplan-Meier) by arm.
3. **Kaplan-Meier** (`PROC LIFETEST`). Curves by the chosen grouping with optional
   confidence bands, censoring marks and number-at-risk table. Also median PFS with its
   confidence interval, 12- and 24-month PFS rates, and the log-rank or Wilcoxon test.
4. **Cox regression** (`PROC PHREG`, `RL`, chosen ties method). Treatment is always in
   the model. **Adjusted** is the prespecified model: treatment, age, sex and stage.
   **Unadjusted** has treatment only, and **Custom** adds any of age, sex, stage, ECOG and
   region. The app never picks a model by its p-value. Categorical covariates are coded
   against the chosen reference levels. A reference that is missing after filtering falls
   back to the first level with a warning, and a covariate with one level is left out
   with a warning. Multi-level covariates get a joint Wald test.
5. **Diagnostics.** For each term, the correlation of its scaled Schoenfeld residuals with
   the rank of event time. Optionally, the `ASSESS PH` supremum test (1,000 resamples).
   Plots: log(-log(survival)) by arm, the treatment effect over time, and deviance
   residuals.
6. **Run status.** One summary table with the key numbers and any notes.

If only one treatment arm is selected, Kaplan-Meier results are still produced. The Cox
model and its diagnostics are skipped with a `WARNING`. The three graphs that depend on
the Cox model (hazard ratios, treatment effect over time, deviance residuals) show a short
note instead, in their usual positions, because the app picks SAS graphs by position. The
log(-log(survival)) plot doesn't need the Cox model and is still drawn. The SAShiny forest
view shows the same note.

## Outputs in the app

| Section | Cards |
|---|---|
| Run | Run summary, SAS log |
| Data | Patient characteristics by arm; events, censoring and follow-up |
| Kaplan-Meier | Survival curves (SAS graph, paired with a SAShiny step chart); median and landmark survival; group comparison; number at risk |
| Cox | Hazard ratios table; forest plot (paired with a SAShiny chart); model fit and global tests |
| Diagnostics | PH tests table; log(-log(survival)); treatment effect over time; deviance residuals |
| Results | Kaplan-Meier estimates table; CSV downloads (KM estimates, hazard ratios, PH tests, analysis dataset) and an RTF report |

## Expected results (sample data, defaults)

Recorded on SAS OnDemand for Academics (SAS 9.4M8). These are estimates from one
simulated sample, so they are not exactly the true values.

| Study | Log-rank p | Median PFS, Control / RX-101 (months) | Adjusted HR, RX-101 vs Control (95% CI) | Treatment PH tests (Schoenfeld; supremum) |
|---|---|---|---|---|
| `RX101-STD` | 0.026 | 13.7 / 17.2 | 0.82 (0.67, 0.99) | p = 0.29; not run by default |
| `RX101-NULL` | 0.82 | 12.2 / 13.1 | 1.02 (0.85, 1.23) | p = 0.41; p = 0.21 |
| `RX101-NPH` | < 0.0001 | 12.1 / 23.2 | 0.56 (0.45, 0.69) | p = 0.011; p < 0.0001: **PH violated** |

In `RX101-NPH` the single hazard ratio of 0.56 averages "no effect for 6 months" and
"strong effect after". The treatment-effect-over-time plot shows the smooth near zero
early and falling later. The log(-log(survival)) curves cross.

## Running it

In the demo app (`Python/examples/demo/app.py` or `R/inst/examples/demo/app.R`), open
the **Survival** tab, keep **Use the sample file** ticked for both datasets, and press
**Run survival analysis**.

From the command line, with the same validation and collection as the app:

```sh
SASHINY_PROFILE=oda SASHINY_ODA_REGION=us1 SASHINY_LICENSE_ACK=true \
  python examples/survival/sas_survival_runner.py --out results/
python examples/survival/sas_survival_runner.py --set study=NPH --set assess_ph=yes \
  --set cox_model=custom --set covariates='["AGE","ECOG","REGION"]'
```

Inputs not set keep the contract defaults. The runner writes tables as CSV, graphs as
PNG/SVG, downloads under `downloads/`, and the SAS log. It needs
`pip install "sashiny[saspy,upload]"`, and Java for ODA or SAS 9.4 IOM. Credentials come
only from `~/.authinfo`.

In SAS Studio, without SAShiny:

```sas
%include "survival_analysis.sas";
proc import datafile="data/adsl.csv"  out=work.adsl  dbms=csv replace; guessingrows=max; run;
proc import datafile="data/adtte.csv" out=work.adtte dbms=csv replace; guessingrows=max; run;
%survival_analysis(study=NPH, assess_ph=yes)
```

## Checked on live SAS

On ODA these combinations ran with no unexpected log messages:

- the defaults
- the NPH study with the resampling test, custom covariates (age, ECOG, region) and RX-101 as the reference
- stage groups with the Wilcoxon test, 90% intervals, no bands or risk table, a 24-month cutoff and Breslow ties
- a small subgroup (stage I women, all randomized subjects, `RX101-NULL`) with an empty custom covariate list
- all studies with a 6-month cutoff, region groups, reference stage III and exact ties
- one arm only: `warning` status, Kaplan-Meier and log(-log(survival)) kept, Cox skipped, every card in its place
- an uploaded ADTTE with no events: a clear `ERROR` message

## Scope of this first version

Included: the three scenarios, Kaplan-Meier with log-rank and Wilcoxon tests, the two
predefined Cox models plus custom covariates and reference levels, Schoenfeld and
supremum PH tests, and CSV/RTF exports.

Not included yet:
- Stratified Cox models, time-dependent covariates (for example treatment × log time),
  and restricted mean survival time, which suits the NPH study.
- Tabs inside one program module. The contract has no tab layout yet, so sections are
  label prefixes.
- A ZIP download of the sample files with a data dictionary: downloads come from SAS
  datasets or ODS (CSV, XLSX, XPT, SAS7BDAT, RTF, PDF). The dictionary is in this README.

## Licensing note

SAS OnDemand for Academics is licensed for learning and some academic or noncommercial
uses. Developing against your own ODA account is different from exposing that account
as the backend of a public app. SAShiny runs programs only on a SAS system you are
licensed to use (`SASHINY_LICENSE_ACK`, spec §6.6).
