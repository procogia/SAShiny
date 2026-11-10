# Conformance fixtures

Both the R package and the Python library MUST pass every fixture here. The fixtures are
**hand-specified**. The reference oracle in `../tools/sashiny_ref.py` only checks that they agree
with each other and with [CONTRACT.md](../CONTRACT.md). It never generates them.

| Folder | What it pins down | Pass condition |
|---|---|---|
| `contracts/valid/<name>/` | Contracts that MUST validate | No `E`/`S` errors |
| `contracts/invalid/<name>/` | Contracts that MUST fail; `expected.json` lists `{code, path}` | Semantic (`S`) errors: exact set. Schema (`E000`): at least the listed paths |
| `values/<name>.json` | Value validation and rendering for a valid contract | `ok`: macro names, values **and order** match. `invalid`: exact `{code, input}` set |
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
