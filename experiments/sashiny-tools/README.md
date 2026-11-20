# sashiny-tools (experiment)

**Not shipped** with the SAShiny R package or the `sashiny` Python package. Refs #130 J7.

A SAShiny contract already declares typed inputs with limits, choices and defaults. This
experiment turns a contract into an LLM tool, so a chat app calls a *validated SAS program*
instead of asking a model to write SAS code.

| Language | Function | Library |
|---|---|---|
| R | `sas_as_tool(contract, engine)` in [`R/sashiny_tools.R`](R/sashiny_tools.R) | [ellmer](https://ellmer.tidyverse.org) |
| Python | `as_tool(contract, engine)` in [`python/sashiny_tools.py`](python/sashiny_tools.py) | [chatlas](https://posit-dev.github.io/chatlas/) |

## Mapping

- Tool name: the contract file stem (`cars_explorer.sashiny.yml` → `cars_explorer`).
- Description: the contract `title` and `description`.
- Arguments, one per input:

  | Input type | Tool argument |
  |---|---|
  | `numeric` | `number`, or `integer` when `integer: true`; `min`/`max` as bounds |
  | `text` | `string` (`max_length`, `pattern` in Python) |
  | `choice` | `string` enum of the static choices (`choices_from`: free string) |
  | `multichoice` | array of the choice enum; `min_selected`/`max_selected` as item limits |
  | `date` | ISO date string (`YYYY-MM-DD`), with resolved `min`/`max` in the description |
  | `daterange` | array of two ISO date strings |
  | `dataset` | **not exposed** (the model cannot upload files) |

  Inputs with a default, and optional inputs, are optional arguments; omitted ones take the
  contract default.
- Result: compact JSON with `run_id`, `status`, the first `ERROR` line of the log, any
  validation `issues`, and table previews (first 20 rows plus `total_rows`). No HTML, plots or
  downloads are sent to the model.

## Safety model

- The model only chooses input values. Every call goes through `sas_run()` / `sashiny.run()`, so
  values are validated (V001–V014) and reach SAS only as `%superq`-quoted macro variables
  (CONTRACT.md §6.3). Invalid arguments come back to the model as V-codes; they never raise
  errors in the app.
- SAS runs the unchanged program; **no generated SAS code is ever submitted**.
- Every call has a `run_id`, returned to the model and kept in the result metadata, so each
  answer can be traced to a SAS log.
- Runs need a licensed SAS system and an explicit licence acknowledgement (CONTRACT.md §6.6),
  exactly like the packages.

## Running

Tests use the internal mock engine, which works only inside test runs:

```sh
# Python (from the repository root)
cd Python && uv run --with chatlas pytest ../experiments/sashiny-tools/python/tests
# R (needs ellmer)
Rscript -e "testthat::test_file('experiments/sashiny-tools/R/tests/test-sashiny-tools.R')"
```

The shinychat demos ([`R/app.R`](R/app.R), [`python/app.py`](python/app.py)) use the
`cars_explorer` contract on SAS OnDemand for Academics. They need an LLM API key, `shinychat`
(R) or Shiny for Python, and `SASHINY_LICENSE_ACK=true`.