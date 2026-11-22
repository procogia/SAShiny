# R / Python parity

Status of every SAShiny feature in the R package (`R/`) and the Python library (`Python/src/sashiny`),
measured against [`spec/CONTRACT.md`](../spec/CONTRACT.md) (release 1.6). The spec and the shared
fixtures under `spec/fixtures` are the contract; where the two languages differ, the spec decides.

Legend: ✅ same behaviour · 🟡 idiomatic difference only (same behaviour, language-shaped API) ·
🔧 gap closed by the parity pass (spec release 1.6) · 🅿 single-language by spec · 📝 deferred.

## 1. Contracts and validation (§1–4)

| Feature | R | Python | Status |
|---|---|---|---|
| Load contract | `sas_contract(path)` | `load(path)` | 🟡 |
| YAML number typing (`-.5`, `1_000`, `017`) | shared rule (spec §1.1) | shared rule (spec §1.1) | ✅ #155, fixed in #157 (fixtures `numeric_yaml_forms`, `e_numeric_yaml_forms`) |
| Validate | `sas_validate(contract, today, error=FALSE)` | `validate(contract, today, raise_error=False)` | 🟡 argument name |
| Schema layer `E000` | ajv | jsonschema | ✅ (messages differ; codes/paths match fixtures) |
| Semantic codes `S001`–`S017` | all | all | ✅ (40 shared fixtures) |
| `S013` program/sample must be a *file* | accepts a directory | file only | 🔧 R |
| Default module id: remove combining marks | 5 Unicode blocks | every combining mark | 🔧 R |
| `default_module_id` public | internal | exported | 🟡 |
| Value codes `V001`–`V014` | all | all | ✅ (shared `values/` fixtures) |
| `""` for `multichoice`/`daterange` | `V002` | `V001` / absent | 🔧 Python (spec §4: non-array is V002) |
| JSON `{}` for `multichoice` | empty selection | `V002` | 🔧 R |
| Huge JSON integer (`1e400` as int) | `V003` | `OverflowError` | 🔧 Python |
| `render_values` `today` default | `Sys.Date()` | required | 🔧 Python (defaults to today) |
| Wrapper / reset code (byte-exact) | `sas_wrapper_code`, `sas_reset_code` | `wrapper_code`, `reset_code` | ✅ (shared `wrapper/` fixtures) |
| Lint `L001`–`L005` | PCRE `\b` (ASCII) | `re` `\b` (Unicode) | 🔧 Python (ASCII word boundaries) |

## 2. Running, engines and pools (§6.1–6.6, §6.11)

| Feature | R | Python | Status |
|---|---|---|---|
| Run | `sas_run(contract, engine, values, today, uploads, run_id)` | `run(contract, engine, values, *, today, uploads, run_id)` | 🟡 (both accept a path and the deprecated swapped order) |
| Backends | `sas_oda`, `sas_viya`, `sas_94_iom`, `sas_94_ssh` | `oda`, `viya`, `sas94_iom`, `sas94_ssh` | 🟡 |
| Bad ODA region error class | rlang error | `EngineError` | 🔧 R (`sashiny_error_engine`) |
| `connect` with backend + stray connection args | error | silently ignored | 🔧 Python (error) |
| Licence acknowledgement | arg, option, env var | arg, env var | 🅿 R option is R-only by spec |
| `engine_version` (saspy + mock) | package version | package version | ✅ #156, fixed in #157; R licence-refused results 🔧 |
| Run timestamps | `…:SSZ` | `…:SSZ` | ✅ #156, fixed in #157 (spec §8.4) |
| `engine_error` text | bare message | `ExcClass: message` | 🔧 Python (bare message) |
| Two concurrent runs on one engine | waits, then `engine busy: another run is in progress` | no guard (first run is cancelled) | 🔧 Python |
| Timeout handling | worker killed, same message | session ended, same message | ✅ |
| Pool | `sas_pool(engine or factory, …)` | `Pool(engine or factory, …)` | 🟡 |
| Pool exhausted | error result, same message | same | ✅ |
| Run on a closed pool | `pool closed` | `pool closed` | 🔧 R (spec §6.5) |
| Pool `choices` when exhausted | `sashiny_error_engine` | `PoolExhausted` (not a `SashinyError`) | 🔧 Python |
| `choices_from` cache cleared on session replacement | yes | pool discard (#152, fixed in #157); `close()` | 🔧 Python `close()` |
| Empty `cached_choices` | used | re-queried | 🔧 Python |
| `connect_from_env` with empty `SASHINY_ODA_REGION` | `us1` | error | 🔧 Python |
| Profile errors | `sashiny_error_deploy` | `ValueError` | 🔧 Python (`DeployError`) |
| Result cache key / TTL / LRU | same | same | ✅ (shared `cache_key.json`) |
| Result-cache store hook | internal `.sashiny_cache_set_store` | `result_cache.set_store` | 🔧 R (exported `sas_cache_set_store()`, `sas_cache_store()`) |
| Mock engine (internal fixture) | `.sashiny_engine_mock` | `_mock.MockEngine` | ✅ (recordings replay in both) |
| In-session PROC PYTHON engine | — | `connect_in_session` | 🅿 Python only (#146 tracks PROC R) |
| `sas_check` / `Result.check` reason text | single space | single space | ✅ #153, fixed in #157 |

## 3. Collection and results (§7, §8)

| Feature | R | Python | Status |
|---|---|---|---|
| Log splitting, trailing blanks | ASCII | ASCII | ✅ #154, fixed in #157 |
| Table `label`/`format`: trim, missing → `""` | yes | no (`NaN` → `"nan"`) | 🔧 Python |
| Plot extraction, paired outputs | same | same | ✅ (shared `plots.json`) |
| Upload blank detection (numeric/date) | ASCII | Unicode | 🔧 Python (ASCII) |
| Declared `character` column conversion | §7.1 cell text | §7.1 cell text | 🔧 spec §7 step 3, shared fixture `uploads/character_cells` |
| CSV download number text | 15 significant digits | `repr` | ✅ allowed by §8.2 ("may differ slightly") |
| Data-frame accessors | `sas_result_table/log/outputs` | `Result.table/log_frame/frames` | 🟡 (shared `frames.json`) |
| Chart spec backends | ggplot2, base, plotly | plotnine, matplotlib, plotly | 🅿 per-language by spec |
| Backend must honour every mapping or error (§8.5) | base R ignores some | matplotlib ignores some + `xlab`/`ylab` | 🔧 R+Python |
| plotly `subtitle` | dropped | shown | 🔧 R |
| plotly `color` + `fill` both set | `fill` wins silently | same | 🔧 R+Python (collection error) |
| `render_chart` `spec` default | `NULL` | required | 🔧 Python (`None`) |

## 4. Shiny module and app (§6.10, §8.6)

| Feature | R | Python | Status |
|---|---|---|---|
| Module UI | `sas_program_ui(id, contract, ui_override, today)` | `program_ui(id, contract, ui_override, *, today)` | 🟡 |
| Module server | `sas_program_server(…, render=, chart_view, chart_toggle, values, hide_inputs, debounce_ms)` | `program_server(…, chart_render=, …)` | 🔧 Python accepts `render=` (alias; `chart_render` kept) |
| Server return | `list(result, status, log)` reactives | same dict | ✅ |
| External values, debounce, hide inputs | yes | yes | ✅ |
| Paired outputs + toggles | yes | yes | ✅ (same JS/CSS) |
| App builder | `sas_app(contracts, engine, title, publish, chart_view, chart_toggle)` | `app(…)` | ✅ |
| Upload transport cap | `shiny.maxRequestSize` | checked in `shiny_values` | 🅿 documented in §7 |
| Streamlit front end | — | `streamlit_app` | 🅿 Python only (#116) |

## 5. Publishing and deployment (§6.7, §6.8)

| Feature | R | Python | Status |
|---|---|---|---|
| Publish to Connect | `sas_publish(app_dir, title, name, account, server, …)` | `publish(app_dir, *, title, name, server, …)` | 🔧 `name` = content name and `server` = nickname in both (see note 2) |
| Publish result | `list(files, excluded, env_vars, deployed)` | `PublishResult(files, excluded, env_vars, command)` | 🟡 |
| Credential exclusion, env vars, licence | same | same | ✅ |
| Deployment targets (generate/apply/doctor) | `sas_deploy`, `sas_deploy_targets`, `sas_deploy_doctor` | `deploy.deploy`, `deploy.targets`, `deploy.doctor` | ✅ (shared `deploy/` fixtures; byte-exact) |
| `streamlit_snowflake`, `databricks_apps` | — | yes | 🅿 Python only (D34) |
| Register custom target | internal | `deploy.register` | 🟡 |
| RStudio addins | `sas_deploy_addin`, `sas_publish_addin` | — | 🅿 R only (RStudio) |

## Notes and limits

1. **Publish `name` in Python.** `rsconnect-python` has no content-name option: it derives the
   content name from the title. `publish(name=)` stages the bundle in a directory called `name`, so
   without a `title` the content name (and title) is `name`, as in R. With both `name` and `title`
   the content name follows the title and Python warns. `server=` is the rsconnect nickname (R:
   `server`); R's `account` has no Python equivalent.
2. **xlsx reader differences (not closed).** R's openxlsx drops fully blank rows (pandas keeps
   them), misreads a text cell with leading or trailing spaces as `xml:space="preserve"> x `, and
   reads xlsx date-times as `Date` (the time is lost), while pandas keeps the time. These sit in the
   readers, not in the character rule, and need their own fix.
3. **Tests.** `R/tests/testthat/test-parity.R` and `Python/tests/test_parity.py` pin the closed
   gaps; the shared fixtures (`values/*`, `collect/log_scope.json`) run in
   both suites and in `spec/tools/check_spec.py`.
