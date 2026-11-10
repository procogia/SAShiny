# Live demo test suite

The demo checklist (`docs/recording-checklist.md`) as automated tests that run
the three demo SAS programs, unchanged, on a real SAS session. The R and Python
suites read the same scenarios from `examples/demo-scenarios.yml`.

## What it checks

For each scenario (the three tracks with their defaults, plus one changed input
per track):

- the session starts and reports a SAS version
- the run returns `status: success` with no engine, input or collection errors
  and no `ERROR:` lines in the program log
- every output is collected: tables have rows and columns, plots are PNG or SVG,
  the report is HTML, and each download has the right filename and file type
  (checked by its first bytes; CSV must have data rows)
- the `.sas` file that ran matches the file on disk (`program_sha256`)
- the recording replays offline with outputs identical to the live run

Across runs:

- WORK is reset between runs (a re-run matches the first run and differs from
  the changed-input run)
- invalid input (`min_msrp = -5`) is rejected before reaching SAS, and the
  session still works afterwards
- an xlsx copy of the AML sample, uploaded as a user file, gives the same tables
- a fresh session gives the same results

Offline (every CI run): the scenario values are valid, the three primary
scenarios equal the UI defaults (so pressing Run untouched matches the
recordings), the checker catches every kind of problem, and any committed
recordings replay and pass the same checks.

## Running it

Credentials come only from `~/.authinfo` (for example `oda user <id> password <pw>`).
IOM connections (ODA, SAS 9.4) need Java 8 or later. Turn on the VPN for
ProCogia Viya or SAS 9.4.

| Variable | Use |
| --- | --- |
| `SASHINY_LIVE=1` | turn the live tests on |
| `SASHINY_PROFILE` | `oda`, `viya` or `sas94` |
| `SASHINY_ODA_REGION` | `us1`, `us2`, `eu1`, `ap1` or `ap2` (default `us1`) |
| `SASHINY_VIYA_URL`, `SASHINY_VIYA_CONTEXT` | Viya |
| `SASHINY_SAS94_HOST`, `SASHINY_SAS94_PORT`, `SASHINY_SAS94_SASPATH` | SAS 9.4 |
| `SASHINY_JAVA` | Java executable, if not on `PATH` or `JAVA_HOME` |
| `SASHINY_RECORD_TO` | where recordings go (default: a temp folder) |

Python, from `Python/`:

```sh
SASHINY_LIVE=1 SASHINY_PROFILE=oda SASHINY_ODA_REGION=eu1 \
  uv run --extra saspy --extra upload --with "pandas<3" pytest tests/live -v
```

R, from `R/tests/` (install the package first with `R CMD INSTALL R`):

```sh
SASHINY_LIVE=1 SASHINY_PROFILE=oda SASHINY_ODA_REGION=eu1 NOT_CRAN=true \
  Rscript -e 'testthat::test_dir("testthat", package = "SAShiny", load_package = "installed", filter = "demo")'
```

## Recording the demo with the suite

Point `SASHINY_RECORD_TO` at `examples/recordings` (from `Python/`, use
`../examples/recordings`) and run one suite. It writes one recording per
scenario, six in total, and only passes when every recording replays. Then
check that nothing is missing:

```sh
cd Python && SASHINY_REQUIRE_RECORDINGS=1 uv run pytest tests/test_demo_scenarios.py
```

Commit `examples/recordings/*.json`. The manual click-through in the checklist
is still worth doing once, since the suite does not drive the Shiny UI.

## When it fails

Each failing scenario lists every problem at once, for example
`stats_csv: dataset WORK.CARS_STATS not found` or `log: SAS log error: ERROR: ...`.
Two set-up problems are caught before saspy starts:

- `Java was not found ...`: install Java, set `JAVA_HOME` or `SASHINY_JAVA`
- `no credentials for 'oda' in ~/.authinfo ...`: add the line it shows. Without
  this check saspy would prompt for a user id on stdin, which hangs a Shiny app.
