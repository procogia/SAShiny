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

### Replay fixtures (`replay/`)

| Path | Pins down (CONTRACT.md §6.6 (a), §8.3) | Pass condition |
|---|---|---|
| `replay.sashiny.yml`, `replay.sas` | The contract and program the recordings were made from | Their SHA-256 are the recordings' `contract_sha256` / `program_sha256` |
| `recordings/<key>.json` | One recording per case; the file name is the §8.3 key of the case's rendered values | |
| `cases.json` | For each case, the replay engine's outcome: replayed (status, `sas_version`, `recorded_at`, `notice`, log, outputs), refused (with the reason), missing, or invalid values | A replay run of `values` with `today` gives `status` and `metadata.recording`, `metadata.engine_error`, `metadata.notice`, `metadata.issues` (`{code, input}`), log and outputs as listed; fields not listed are not checked |

The recordings are hand-written fixture data, not output of a real SAS run. Their file names are
computed from §8.3 (`check_spec.py` recomputes them), and the contract and program use LF line endings
(`.gitattributes`) so their SHA-256 is the same on every platform. Like `deploy/`, this folder is not
copied to `R/inst/spec` (its file paths are longer than the 100 bytes a CRAN tarball allows); the R
tests skip these cases outside the source repository.

### Deployment fixtures (`deploy/`)

| Path | Pins down (CONTRACT.md §6.8) | Pass condition |
|---|---|---|
| `profiles.json` | Profile validation, kind, egress endpoints, Java need, plain env vars and secret names | Valid cases match `expected` exactly (env order included); invalid cases raise an error starting with `expected_error` |
| `errors.json` | `generate()` error order and messages (VPN, licence, language, port, target, unsafe host) | Error message starts with `expected_error`; `null` means no error |
| `<case>/case.json`, `<case>/app/`, `<case>/expected/` | One `generate()` run: copy `app/` to a temporary folder, add `add_files`, generate with `version` | Result fields match `expected`; every file under `expected/` matches the generated file byte for byte |

The `streamlit_*` cases are Python only (spec §6.8.5); the R package skips them.

### Streamlit fixtures (`streamlit/`)

| Path | Pins down (CONTRACT.md §6.9) | Pass condition |
|---|---|---|
| `widgets.json` | The Streamlit widget, keyword arguments, options and labels for every input type and widget variant | `widget_spec(input, today, loaded)` matches `expected` (dates as ISO strings); Python only |

Credential files are never committed. A case lists them in `add_files`, and the test creates them in
its temporary copy of `app/`.
