# Live QA checklist for the 0.3.1 features

Mock and fake-session tests in CI prove the wiring only. These checks need a real, licensed SAS
system (ODA, Viya or SAS 9.4) and are **never** run by CI, CRAN or PyPI. Credentials come only from
`~/.authinfo` or the platform's secret store. Running a check acknowledges the SAS licence for that
system (`SASHINY_LICENSE_ACK=true`).

Testing is split evenly. Igor covers the R side of each feature plus SAS 9.4; Shreya covers the
Python side plus Viya and PROC PYTHON. Each check that exists in both languages is run once per
language, so both owners exercise it.

Fill in **Status** (`verified` / `failed` / `blocked`), **Date**, **Backend** and **Evidence** (run
ids, timings, log excerpts without secrets). Open an issue for every failure and link it here.

| # | Feature (PR) | Check | Language | Owner | Backend | Status | Date | Evidence |
|---|---|---|---|---|---|---|---|---|
| 1 | Session reuse (#133, #134) | `test-live-session-reuse.R`: 10 runs on one engine reuse one SAS process; pool of 2 uses 2; record median and p90 | R | Igor (@igor-procogia) | ODA `us1` | | | |
| 2 | Session reuse (#133) | `tests/live/test_live_session_reuse.py`, same checks | Python | Shreya (@shreya-sharma-procogia) | ODA `us1` | | | |
| 3 | Persistent worker (#134) | In `sas_app()`, a 60 s run in one browser tab does not block a second tab; closing the first tab cancels its run | R | Igor | SAS 9.4 IOM | | | |
| 4 | Choices cache (#138) | A `choices_from` contract: the second browser session shows choices without a SAS query (log has one `_sx_choices` step); after `choices_ttl_seconds` they reload | R | Igor | SAS 9.4 IOM | | | |
| 5 | Choices cache (#138) | Same, Shiny for Python | Python | Shreya | Viya | | | |
| 6 | Data frames (#136) | `sas_result_table()` on `cars_explorer`: labels and formats match PROC CONTENTS | R | Igor | ODA `us1` | | | |
| 7 | Data frames (#136) | `Result.table()` / `frames()` on `cars_explorer`, same comparison | Python | Shreya | ODA `us1` | | | |
| 8 | Classed errors (#137) | A wrong host gives `sashiny_error_engine`; an ERROR in the program gives `sas_check()` failure text matching Python | R | Igor | SAS 9.4 SSH | | | |
| 9 | Classed errors (#137) | Same: `EngineRuntimeError`, `Result.check()` text identical to R | Python | Shreya | Viya | | | |
| 10 | Backend constructors (#140) | `sas_connect(sas_94_iom(...))`, `sas_94_ssh(...)`, `sas_oda()`, `sas_viya(...)` each run `minimal` | R | Igor | all available | | | |
| 11 | Backend constructors (#140) | `connect(sas94_iom(...))`, `sas94_ssh`, `oda()`, `viya(...)` each run `minimal` | Python | Shreya | all available | | | |
| 12 | Module values (#141) | `examples/parent-filter/app.R`: changing the filter reruns after about 500 ms; the hidden origin control stays hidden; an invalid value shows V-codes | R | Igor | ODA `us1` | | | |
| 13 | Module values (#141) | `examples/parent-filter/app.py`, same checks | Python | Shreya | ODA `us1` | | | |
| 14 | Result cache (#143) | With `run.cache: true`, a repeated run returns at once with `cache_hit` and the original `run_id`; the SAS log shows one run; an upload change reruns | R | Igor | SAS 9.4 IOM | | | |
| 15 | Result cache (#143) | Same, Python | Python | Shreya | Viya | | | |
| 16 | PROC PYTHON probe (#147, #128 step 1) | Submit `Python/tests/live/procpython/probe.sas`; post `sashiny_probe.json` on #128 | Python | Shreya | Viya | | | |
| 17 | PROC PYTHON parity (#147) | `tests/live/test_procpython_live.py` with the probe output | Python | Shreya | Viya | | | |
| 18 | PROC PYTHON on 9.4M9 (#147) | Repeat check 16 on SAS 9.4M9 with the PROC PYTHON hot fix, if available | Python | Igor | SAS 9.4M9 | | | |
| 19 | Versions (#148) | `sas_info()` and `sashiny.info()` on the released 0.3.1 packages print the same spec release | R + Python | Igor | none | | | |
| 20 | LLM tools experiment (#145) | `experiments/sashiny-tools` demo answers a price question, and every answer quotes a `run_id` found in the SAS log | R + Python | Shreya | ODA `us1` | | | |

Ten checks each. Commands for checks 1, 2, 16 and 17 are in `CONTRIBUTING.md` ("Live checks").