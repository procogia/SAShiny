# Conformance fixtures

Both the R package and the Python library MUST pass every fixture here. The fixtures are
**hand-specified**. The reference oracle in `../tools/sashiny_ref.py` only checks that they agree
with each other and with [CONTRACT.md](../CONTRACT.md). It never generates them.

| Folder | What it pins down | Pass condition |
|---|---|---|
| `contracts/valid/<name>/` | Contracts that MUST validate | No `E`/`S` errors |
| `contracts/invalid/<name>/` | Contracts that MUST fail; `expected.json` lists `{code, path}` | Semantic (`S`) errors: exact set. Schema (`E000`): at least the listed paths |
| `values/<name>.json` | Value validation and rendering for a valid contract | `ok`: macro names, values **and order** match. `invalid`: exact `{code, input}` set |
| `lint/<name>/` | Advisory lint findings (§10) for a contract and its program | `expected.json` `findings` (`{code, path}`) match exactly, in order |
| `wrapper/<name>/` | Byte-exact generated SAS | `expected_reset.sas` (absent when `reset_work: false`) and `expected_main.sas` match byte-for-byte, with `run_id = fixture` |
| `frames/cases.json` | Canonical CSV of data frames supplied for dataset inputs (§7.1) | Each case's data frame is written as exactly its `csv` text, in R and Python; read back as a `csv` upload (§7), that text has one row per value (blank lines of a one-column file are rows) |

Conventions:
- `today` is fixed at `2026-11-11` in fixtures, so `"today"` in contracts is deterministic.
- `choices_from` in a value case supplies the choices the engine would have read from SAS.
- `uploads` maps dataset input ids to `true` when a file was supplied.
- Expected SAS files use LF line endings, end with a newline and have no trailing spaces.
- `wrapper/program_entry/program.sas` starts with a UTF-8 BOM, uses CRLF and has no final newline,
  on purpose. Do not "fix" it.

Run the checks from the repository root:

```sh
uv run --with jsonschema --with pyyaml python spec/tools/check_spec.py
```

When adding a fixture, write the expected output by hand from CONTRACT.md first, then run the check.

### Collection fixtures (`collect/`)

| File | Pins down (CONTRACT.md §8) |
|---|---|
| `log_scope.json` | Log splitting, trailing-whitespace removal, `program`/`full` scope, level classification (§8.2 log) |
| `plots.json` | Plot extraction from the ODS HTML: data-URI `<img>` and inline `<svg>`, document order, `select` (§8.2 plot) |
| `recording_key.json` | The recording key text and its SHA-256 (§8.3) |

`key_text` in `recording_key.json` is hand-written from §8.3. `key` is its SHA-256.

### Deployment fixtures (`deploy/`)

| Path | Pins down (CONTRACT.md §6.8) | Pass condition |
|---|---|---|
| `profiles.json` | Profile validation, kind, egress endpoints, Java need, plain env vars and secret names | Valid cases match `expected` exactly (env order included); invalid cases raise an error starting with `expected_error` |
| `errors.json` | `generate()` error order and messages (VPN, licence, language, port, target, unsafe host) | Error message starts with `expected_error`; `null` means no error |
| `<case>/case.json`, `<case>/app/`, `<case>/expected/` | One `generate()` run: copy `app/` to a temporary folder, add `add_files`, generate with `version` | Result fields match `expected`; every file under `expected/` matches the generated file byte for byte |

The `streamlit_*` cases are Python only (spec §6.8.5); the R package skips them.

### Upload fixtures (`uploads/`)

| Path | Pins down (CONTRACT.md §7) | Pass condition |
|---|---|---|
| `character_cells/case.json`, `cells.xlsx` | Declared `character` columns take the §7.1 rule 5 text of each native cell (step 3) | Every listed column of the read file equals `expected`, cell for cell |
| `xlsx_reading/case.json`, `rows.xlsx` | xlsx reading (step 1): blank rows kept, text spaces kept, date-formatted columns as date-times | Same as above |

### Streamlit fixtures (`streamlit/`)

| Path | Pins down (CONTRACT.md §6.9) | Pass condition |
|---|---|---|
| `widgets.json` | The Streamlit widget, keyword arguments, options and labels for every input type and widget variant | `widget_spec(input, today, loaded)` matches `expected` (dates as ISO strings); Python only |

Credential files are never committed. A case lists them in `add_files`, and the test creates them in
its temporary copy of `app/`.
