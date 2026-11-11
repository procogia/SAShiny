# SAShiny Contract Specification — Version 1

Status: **Draft 1 (phase 1)**. This document is normative for both the R package and the Python library.
The key words MUST, MUST NOT, SHOULD and MAY are used as described in RFC 2119.

The machine-readable structure is [`sashiny.schema.json`](sashiny.schema.json) (JSON Schema 2020-12).
This document adds what a schema cannot express: semantic rules, value validation, value rendering,
the generated SAS wrapper, the run protocol and result parsing. Conformance is checked by the shared
fixtures in [`fixtures/`](fixtures).

---

## 1. Files

A SAShiny program is a pair of files in the same directory:

| File | Owner | Rule |
|---|---|---|
| `analysis.sas` | SAS author | **Never modified, rewritten or reformatted by SAShiny.** |
| `analysis.sashiny.yml` | App author | The contract. UTF-8, YAML 1.2 core schema subset (see 1.1). |

The contract's `program` field points at the SAS file, relative to the YAML file.

### 1.1 YAML subset
Implementations MUST load contracts with a safe loader (no custom tags, no object construction).
Authors MUST NOT rely on YAML 1.1 implicit typing. In particular, quote values such as `yes`, `no`,
`on`, `off`, `Y`, `N` and ISO dates when they are meant as strings. Implementations MUST treat
contract dates as strings matching `YYYY-MM-DD` and MUST NOT accept YAML timestamp objects.
Mapping order is significant: inputs and outputs are processed in the order written.

---

## 2. Structure (summary)

```yaml
sashiny: 1                 # required, schema version
program: analysis.sas      # required
id: analysis               # optional module id
title: Analysis title      # required
description: ...           # optional
version: "1.0"             # optional, author's own version
inputs:  {<id>: <input>}   # optional
outputs: {<id>: <output>}  # required, at least one
run:     {...}             # optional
ui:      {...}             # optional
```

Identifiers (`id`, input and output keys) match `^[a-z][a-z0-9_]{0,31}$` and are used directly as
Shiny ids. The default module `id` is derived from the program file name. Take the base name without
the `.sas` extension, lower-case it, replace each character outside `[a-z0-9_]` with `_`, prefix `p_`
if it does not start with a letter, and truncate to 32 characters.

### 2.1 Input types

| `type` | Value (JSON form) | Key fields |
|---|---|---|
| `numeric` | number | `min`, `max`, `step`, `integer`, `default` |
| `text` | string | `max_length` (256), `pattern`, `render` (`raw`), `default` |
| `choice` | string | `choices` or `choices_from`, `widget`, `render` (`raw`), `default` |
| `multichoice` | array of strings | `choices` or `choices_from`, `render` (`quoted`), `separator` (`space`), `count_macro`, `min_selected` (1), `max_selected`, `default` |
| `date` | `"YYYY-MM-DD"` | `min`, `max`, `render` (`literal`), `default` |
| `daterange` | `["YYYY-MM-DD", "YYYY-MM-DD"]` | `macro: [start, end]`, `min`, `max`, `render`, `default` |
| `dataset` | uploaded file | `target` (WORK only), `accept`, `max_size_mb` (50), `columns`, `sample`, `macro` |

Every input has `label` (required), `help` and `optional` (default `false`).
Every non-dataset input sets one macro variable named by `macro`, which defaults to the input id
upper-cased. The exceptions are `daterange`, which sets two (default `<ID>_START`, `<ID>_END`), and
`multichoice` with `count_macro`, which sets one more.
A `dataset` input sets a macro variable only when `macro` is given.

A choice item is either a string (value = label) or `{value, label}`.
`choices_from` reads choices when the session starts from `dataset` (`value_column`, optional
`label_column`, `max_choices` ≤ 1000). The engine generates that query from validated SAS names
only (see 6.4).

### 2.2 Output types

| `type` | Source | Key fields |
|---|---|---|
| `table` | dataset after the run | `from` (`lib.member`), `columns`, `max_rows` (10000), `formatted` (false) |
| `plot` | ODS graphics of the run | `select` (1-based position; omit for all) |
| `html` | full ODS HTML listing | — |
| `log` | SAS log | `scope`: `program` (default) or `full` |
| `download` | file | `format`: `csv`, `xlsx`, `xpt`, `sas7bdat` (need `from`); `rtf`, `pdf` (ODS, no `from`); `filename` |

Every output has optional `label` and `help`.

### 2.3 `run`

| Field | Default | Meaning |
|---|---|---|
| `entry` | `program` | `program`: submit the program text as-is. `macro`: submit the program text (which defines a macro), then call it. |
| `macro` | — | Macro to call when `entry: macro`. Each input's macro name is passed as a keyword parameter of the same name. |
| `timeout_seconds` | `300` | Wall-clock limit for the whole run. |
| `reset_work` | `true` | Empty `WORK` and delete previously injected macro variables before the run. |

### 2.4 `ui`

`layout` (`sidebar` \| `top`), `order` (input ids in display order; unlisted inputs follow in contract
order), `run_label` (`"Run"`), `auto_run` (`false`). These are hints for auto-generated UI only.

---

## 3. Contract validation

Validation has two layers. Implementations MUST report every error they find, not only the first.
Each error has a `code`, a JSON-pointer-style `path` (e.g. `/inputs/min_msrp/default`) and a message.

### 3.1 Schema layer
The contract MUST validate against `sashiny.schema.json`. All schema failures share code **`E000`**.

### 3.2 Semantic layer

| Code | Rule |
|---|---|
| `S001` | Macro variable names (including defaults, both daterange names, `count_macro` and dataset `macro`) MUST be unique, case-insensitively. |
| `S002` | Default macro names derived from input ids MUST NOT be reserved (start with `SYS`, `SASHINY` or `_SX_`, any case). |
| `S003` | `min` MUST be ≤ `max` (numeric, date, daterange). |
| `S004` | `default` MUST pass value validation (section 4) for its input. |
| `S005` | `choices` values MUST be unique within an input. |
| `S006` | For `multichoice`: `min_selected` ≤ `max_selected` ≤ number of static choices (when `choices` is used). |
| `S007` | `render: bare` (multichoice) requires every static choice value to be a SAS name or a numeric literal. |
| `S008` | `download` with `format` `csv`, `xlsx`, `xpt` or `sas7bdat` MUST have `from`; with `rtf` or `pdf` it MUST NOT. |
| `S009` | `run.entry: macro` requires `run.macro`; `run.macro` without `entry: macro` is an error. |
| `S010` | Dataset input `target`s MUST be unique, case-insensitively. |
| `S011` | Input ids and output ids share one namespace and MUST NOT collide. |
| `S012` | `ui.order` entries MUST name existing inputs. |
| `S013` | The `program` file MUST exist and be readable. A `sample` file, if given, MUST exist. |
| `S014` | `pattern` MUST compile and use only the portable regex subset (3.3). |
| `S015` | `numeric` with `integer: true`: `min`, `max` and `default` MUST be integers. |
| `S016` | Dataset `columns` names MUST be unique, case-insensitively. |

### 3.3 Portable regex subset
`pattern` is matched against the **whole** value (implementations anchor it). It MUST be valid and
mean the same thing in ECMAScript, Python `re` and R's PCRE (`perl = TRUE`). Allowed: literals,
`.`, character classes `[...]` and `[^...]`, `\d \w \s \D \W \S`, quantifiers `* + ? {m} {m,} {m,n}`
(greedy only), groups `( )` and `(?: )`, alternation `|`, escapes of metacharacters.
Not allowed: look-around, back-references, named groups, inline flags, possessive or lazy quantifiers,
Unicode property classes, `^`/`$` inside the pattern.

---

## 4. Value validation

Values arrive from the UI in the JSON form of 2.1. Implementations MUST validate before rendering and
MUST reject the whole run if any value is invalid, reporting all invalid inputs.

| Code | Condition |
|---|---|
| `V001` | Required input missing, `null`, empty string, or an empty selection when `min_selected` ≥ 1. |
| `V002` | Wrong JSON type for the input type. |
| `V003` | Numeric outside `[min, max]`, or not finite (`NaN`, `±Inf`). |
| `V004` | Value not among the allowed choices. |
| `V005` | Text does not match `pattern`. |
| `V006` | Text longer than `max_length` (counted in Unicode code points, after trimming). |
| `V007` | Text or choice contains a control character (U+0000–U+001F, U+007F–U+009F). |
| `V008` | Multichoice selection count outside `[min_selected, max_selected]`, or duplicate selections. |
| `V009` | Date not a real calendar date, or outside `[min, max]`. |
| `V010` | Daterange start after end. |
| `V011` | Value supplied for an id that is not an input of this contract. |
| `V012` | `integer: true` and value is not an integer. |
| `V013` | Rendered macro value longer than 32 000 bytes (UTF-8). |
| `V014` | Upload: extension not in `accept`, file larger than `max_size_mb`, unreadable, or missing a declared column. |

Normalisation happens **before** validation and is part of the contract:
- Text values are trimmed of leading and trailing whitespace (Unicode `White_Space`).
- `"today"` in `default`, `min` or `max` is resolved once, when the session starts, to the client's
  local date in the app's configured time zone (default: the server's time zone).
- An `optional` input with no value is **absent**. It is not an error and it renders as section 5.6.

---

## 5. Value rendering

Rendering turns a validated value into the **logical text** of each macro variable. Fixtures specify
this text exactly. Section 6 defines how the text is delivered to SAS safely; nothing in this section
needs to be SAS-escaped.

### 5.1 numeric
- Integers with absolute value < 10^15 are written with no decimal point or exponent: `20000`, `-3`.
- Otherwise use C `printf("%.15g")`, then upper-case `e` to `E`. Examples: `0.5`, `1.25`, `1E+20`, `1.5E-07`.
- `-0` renders as `0`.

### 5.2 text and choice
| `render` | Result for `O'Brien & Co` |
|---|---|
| `raw` (default) | `O'Brien & Co` |
| `quoted` | `'O''Brien & Co'` (wrap in `'`, double each `'`) |
| `dquoted` | `"O'Brien & Co"` (wrap in `"`, double each `"`) |

`quoted` is recommended for values that go into SAS string comparisons, because SAS does not resolve
macro triggers inside single quotes. `quoted` and `dquoted` renderings are also macro-inert (the macro
processor does not resolve `&` or `%` inside SAS string literals), so they are emitted without
`%superq` in the wrapper (§6.3). Only `raw` text/choice values need `%superq`.

### 5.3 multichoice
Each selected value is rendered with `render` (`quoted` default, `dquoted`, or `bare` = as-is). The
values are joined in **the order of the choice list**, not selection order, with `" "` (`separator: space`)
or `", "` (`separator: comma`). An empty selection renders as the empty string.
`count_macro`, if given, receives the number of selected values (`0`, `1`, ...).

Example: choices `[Asia, Europe, USA]`, selection `[USA, Asia]`, `quoted` + `space` → `'Asia' 'USA'`.

### 5.4 date and daterange
| `render` | Result for 2026-11-11 |
|---|---|
| `literal` (default) | `'11NOV2026'd` |
| `date9` | `11NOV2026` |
| `iso` | `2026-11-11` |
| `sasdate` | `24421` (days since 1960-01-01) |

Month abbreviations are English and upper-case. `daterange` renders start and end independently into
its two macro variables.

### 5.5 dataset
When a file is supplied, the `macro` variable (if declared) receives the upper-cased `target`, e.g.
`WORK.ADSL`.

### 5.6 absent optional inputs
Every macro variable of an absent optional input receives the empty string. A `count_macro` receives `0`.

### 5.7 macro names
Macro names are emitted **upper-cased** and in contract order. For each input that order is: the main
macro, then (`daterange`) end, then (`multichoice`) `count_macro`.

---

## 6. Generated SAS

### 6.1 Run protocol
A run is a fixed sequence of engine steps. Steps 1 and 3 are SAS submissions defined below.
Steps 2 and 4 are engine operations.

1. **Reset** submission (only if `run.reset_work` is true).
2. **Upload** each supplied dataset input to its `target` (column conversion: section 7).
3. **Main** submission: the wrapper with the program text embedded verbatim.
4. **Collect** outputs (section 8). A collect failure never changes the SAS status of the run.

A run has a `run_id` matching `^[A-Za-z0-9-]{1,36}$`, generated by the engine (UUID recommended).
Fixtures use `fixture`.

### 6.2 Reset submission
```sas
/* SAShiny 1 reset */
proc datasets library=work kill nolist nowarn;
quit;
%symdel <NAMES> / nowarn;
```
`<NAMES>` is the space-separated list of every macro name this contract can set, in the order of 5.7.
If the contract sets no macro variables, the `%symdel` line is omitted.

### 6.3 Main submission (wrapper)
The wrapper is produced **byte-for-byte** as below: LF line endings, no trailing spaces, two-space
indentation inside `data _null_`. `<...>` are placeholders. Bracketed lines are conditional.

```sas
/* SAShiny 1 wrapper: generated, do not edit */
%put NOTE: SASHINY-BEGIN run=<run_id>;
%let syscc = 0;
[data _null_;                                   ] only if at least one macro is set
[  call symputx('<NAME>', '<VALUE>', 'G');      ] one line per macro, order of 5.7
[run;                                           ]
[%let <NAME> = %superq(<NAME>);                 ] only for `raw` text/choice macros, same order
[ods <fmt>(id=<output_id>) file="%sysfunc(pathname(work))/sashiny_<output_id>.<fmt>";] one per rtf/pdf download, contract order
%put NOTE: SASHINY-BEGIN-PROGRAM;
<PROGRAM TEXT, verbatim>
[%<MACRO>(<NAME1>=&<NAME1>, <NAME2>=&<NAME2>, ...);] only if run.entry is macro; all input macro names, order of 5.7
%put NOTE: SASHINY-END-PROGRAM;
[ods <fmt>(id=<output_id>) close;               ] one per rtf/pdf download, contract order
%put NOTE: SASHINY-END run=<run_id> syscc=&syscc;
```

Rules:
- `<VALUE>` is the rendered value (section 5) with every `'` doubled. Because it sits in a **single-quoted**
  SAS literal, the macro processor never sees `&` or `%` in user data.
- The `%superq` re-store is emitted **only** for `raw` text/choice values, which are unquoted and could
  otherwise trigger macro execution. Values that are already SAS string literals (`quoted`, `dquoted`),
  numeric literals, date literals, and validated `bare` values (SAS names or numeric literals) are
  emitted directly without `%superq`, because they are already inert: the macro processor does not
  resolve `&` or `%` inside SAS string literals, and the compiler unquotes them where needed (for
  example in `WHERE` clauses). Applying `%superq` to those values would keep them macro-quoted and
  break `WHERE` clauses (see §9).
- `<PROGRAM TEXT>` is the program file decoded as UTF-8, a leading BOM removed, and CRLF/CR line endings
  converted to LF. Nothing else changes. A newline is inserted after the program text if it does not end
  with one. The file on disk is never changed.
- With `entry: macro`, if the contract sets no macro variables the call is `%<MACRO>();`. Dataset-input
  macros are included in the call only when declared.
- Each `rtf`/`pdf` download opens its own ODS destination instance, `id=` set to the output id, so several
  downloads of the same format can coexist. `<fmt>` is `rtf` or `pdf`.

### 6.4 `choices_from` query
At session start, for each input with `choices_from`, the engine submits:

```sas
proc sql outobs=<max_choices> noprint;
  create table work._sx_choices as
  select distinct <value_column> [, <label_column>]
  from <dataset>
  where not missing(<value_column>)
  order by <value_column>;
quit;
```
It then reads `work._sx_choices` and deletes it. All names are schema-validated SAS names.

### 6.5 Run status
The engine reads the log of the main submission:

| Status | Condition |
|---|---|
| `error` | `SASHINY-END` sentinel missing (program ended the session, unbalanced quotes, timeout), or `syscc` > 4, or any log line starting with `ERROR` |
| `warning` | otherwise, any log line starting with `WARNING`, or `syscc` = 4 |
| `success` | otherwise |

A timeout MUST abort the SAS session. The pool MUST then discard and replace that session.

---

## 7. Dataset upload conversion

1. Read the file by extension: `csv` (UTF-8, comma, header row, RFC 4180), `xlsx` (first sheet, header
   row), `xpt` (SAS transport v5/v8), `sas7bdat`.
2. Column names: replace characters outside `[A-Za-z0-9_]` with `_`; prefix `_` if the first character is
   a digit; truncate to 32 bytes; resolve case-insensitive duplicates by suffixing `_2`, `_3`, ... (truncating
   further to fit). Declared `columns` are matched case-insensitively **after** this step.
3. Declared column types: `numeric` (parse as number, empty = missing; unparseable = `V014`), `character`,
   `date` (ISO `YYYY-MM-DD`, or a native date type; stored as SAS date with format `DATE9.`).
4. Undeclared columns: native numeric/date types are kept. In `csv`, a column whose non-empty values all
   parse as numbers becomes numeric, otherwise character.
5. The result is written to `target`. Column order is preserved.
6. A supplied dataset input is either a user file or, if the UI offers it, the contract's `sample` file.
   Both go through steps 1–5.

---

## 8. Result collection

Collection is step 4 of the run protocol (6.1). It happens after the main submission and in contract output
order. A failure collecting one output MUST NOT change the run status or stop collection of the other
outputs. The failed output's value is `{"error": "<message>"}`, and the message is also appended to
`metadata.collect_errors`.

### 8.1 Output values

Each output has a **language-neutral JSON value**. Engines return it, the mock engine replays it, and
recordings store it (8.3), so R and Python see identical data.

| Output | Value |
|---|---|
| `table` | `{"columns": [{"name", "type", "label", "format"}], "rows": [[...], ...], "total_rows": int or null, "truncated": bool, "formatted": bool}` |
| `plot` | `[{"mime": "image/png" \| "image/svg+xml" \| "image/jpeg" \| "image/gif", "data": "<base64>"}, ...]` |
| `html` | The ODS HTML document of the main submission, as a string |
| `log` | `[{"level": "error" \| "warning" \| "note" \| "text", "text": "<line>"}, ...]` |
| `download` | `{"filename": "<name>.<ext>", "mime": "<type>", "data": "<base64>"}` |

Table details:
- `type` is `"numeric"` or `"character"`. `label` and `format` are `""` when SAS has none.
- With `formatted: false`, numeric cells are JSON numbers, or `null` for SAS missing values. Character
  cells are strings with trailing blanks removed. SAS dates stay numbers.
- With `formatted: true`, every cell is the string SAS displays (`vvalue`), with leading and trailing
  blanks removed.
- `total_rows` is the logical observation count (`nlobs`). It is `null` when SAS cannot report it, for
  example for views. `truncated` is `total_rows > max_rows`.

### 8.2 Collection protocol

`<LIB>` and `<MEM>` are the upper-cased parts of `from`. `<WORK>` is `%sysfunc(pathname(work))`.
Remote paths join a directory and a file name with `\` if the directory contains a `\`, otherwise with `/`.
Temporary members (`work._sx_*`) are deleted after use.

**table**
1. Read column metadata:
   ```sas
   proc sql noprint;
     create table work._sx_cols as
       select varnum, name, type, format, label
       from dictionary.columns
       where libname = "<LIB>" and memname = "<MEM>"
       order by varnum;
     create table work._sx_nobs as
       select nlobs from dictionary.tables
       where libname = "<LIB>" and memname = "<MEM>";
   quit;
   ```
   If `work._sx_cols` is empty, the error is `dataset <LIB>.<MEM> not found`.
2. The selected columns are `columns`, matched case-insensitively and kept in the order listed, or all
   columns in `varnum` order. An unknown column is an error.
3. `formatted: false`: read `<LIB>.<MEM>` with data-set options `obs=<max_rows>` and `keep=<columns>`.
4. `formatted: true`: run the step below, then read `work._sx_fmt` and rename `_sx_c<i>` back to the
   original column names. `<k>` is the number of selected columns.
   ```sas
   data work._sx_fmt;
     set <LIB>.<MEM>(obs=<max_rows> keep=<col1> ... <colk>);
     length _sx_c1-_sx_c<k> $512;
     _sx_c1 = strip(vvalue(<col1>));
     ...
     keep _sx_c1-_sx_c<k>;
   run;
   ```

**plot**: The plots are the images embedded in the `html` document, in document order. Collect each
`<img>` whose `src` is a `data:image/...;base64,...` URI as-is, and each inline `<svg>...</svg>` element
base64-encoded with mime `image/svg+xml`. With `select: k` the value is a one-item list. If fewer than
`k` images exist, collection fails for that output.

**html**: The ODS HTML listing returned by the main submission.

**log**: Split the main-submission log on line breaks (`CRLF`, `CR` or `LF`). If the log ends with a line
break, there is no empty final line. Drop trailing whitespace from each line.
`program` scope keeps the lines strictly between the line equal to `NOTE: SASHINY-BEGIN-PROGRAM` and the
line equal to `NOTE: SASHINY-END-PROGRAM`, or every line after BEGIN if END is missing. Source echo lines
never match, because SAS prefixes them with line numbers. `full` keeps every line. Each line's `level`
is `error`, `warning` or `note` if it starts with `ERROR`, `WARNING` or `NOTE`, otherwise `text`.

**download**: The file name is `<filename or output id>.<ext>`.

| `format` | Produced by | MIME |
|---|---|---|
| `csv` | Client: all rows of `from` (raw values, at most 1 000 000), header row, UTF-8, comma, LF line ends, RFC 4180 quoting, missing = empty field | `text/csv` |
| `xlsx` | Client: same rows, first sheet named after `<MEM>` | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| `xpt` | Client: SAS transport version 5 if `<MEM>` and every column name are at most 8 characters, otherwise version 8 | `application/x-sas-xport` |
| `sas7bdat` | Server: download `pathname(<LIB>)` joined with lower-case `<MEM>` + `.sas7bdat` | `application/x-sas-data` |
| `rtf` / `pdf` | Server: download `<WORK>` joined with `sashiny_<output_id>.<fmt>`, written by the wrapper (6.3) | `application/rtf` / `application/pdf` |

Numeric formatting in client-produced files may differ slightly between implementations.

### 8.3 Recordings

A recording replays a run without SAS. It is the offline fallback and the source of examples and
tests. It is a UTF-8 JSON file `<key>.json`:

```json
{"sashiny_recording": 1, "status": "...", "log": "<full main-submission log>",
 "outputs": {"<output_id>": <value from 8.1>}, "sas_version": "...",
 "contract_sha256": "...", "program_sha256": "...", "macros": {"NAME": "VALUE"},
 "recorded_at": "<UTC ISO 8601>"}
```

`<key>` is the lower-case hex SHA-256 of this UTF-8 text, built line by line with LF endings:

```
sashiny-recording-key 1
contract <contract_sha256>
macro <NAME>=<VALUE>          one line per rendered macro, in 5.7 order
upload <input_id> <sha256>    one line per supplied dataset input, contract order; sha256 of the file bytes
```

The key depends only on the contract bytes, the rendered values and the uploaded files. A recording
made by either language therefore replays in both. A mock engine with no matching recording returns
status `success` with empty outputs and sets `metadata.recording` to `"missing"`.

### 8.4 Run metadata

Every result carries run metadata: `run_id`, `contract_sha256` (of the YAML bytes), `program_sha256`
(of the program file bytes as stored on disk), rendered macro values, start/end timestamps (UTC, ISO 8601),
engine name and version, SAS version (`&SYSVLONG`), status, and `collect_errors` (list, possibly empty).

---

## 9. Known constraints (documented, not errors)

- If the program sets one of the injected macro variables itself (e.g. `%let min_msrp = 5;`), the
  program's value wins. Lint reports this (`L001`) by scanning for `%let <NAME>` and
  `call symput[x]('<NAME>'`, except assignments inside a
  `%if not %symexist(<NAME>) %then %do; ... %end;` guard. Programs written for standalone use SHOULD guard defaults with
  `%if not %symexist(NAME) %then %do; %let NAME = ...; %end;` (SAS 9.4M5+ open-code `%if`).
- A program that ends the session (`endsas;`) or leaves unbalanced quotes produces status `error`
  (missing END sentinel).
- Macro-quoted values are **not** automatically unquoted when passed to the compiler. In particular,
  `WHERE` clauses do not unquote them, so a macro-quoted value such as `'Asia' 'Europe' 'USA'` causes a
  syntax error in `where origin in (&NAME)`. For this reason SAS-literal values are emitted without
  `%superq` (see §6.3), and only `raw` text/choice values are macro-quoted. A program may use
  `%unquote(&NAME)` where a quoted token must be resolved, but it MUST NOT be required for ordinary
  `WHERE` clauses.

## 10. Lint (advisory)

| Code | Finding |
|---|---|
| `L001` | Program assigns an injected macro variable outside a `%symexist` guard (section 9). |
| `L002` | Injected macro variable never referenced in the program (`&NAME` not found, case-insensitive). |
| `L003` | `table`/`download` `from` dataset never created in the program and not a dataset input target or a permanent library. |
| `L004` | More than one `rtf`/`pdf` download: each receives the same output; usually unintended. |
| `L005` | `entry: macro` but `%macro <MACRO>` not found in the program. |

## 11. Versioning

`sashiny: 1` will only ever receive backward-compatible additions: new optional fields with defaults
that preserve existing behaviour. Any breaking change becomes `sashiny: 2`. Wrapper changes that alter
generated bytes require a new wrapper version line (`/* SAShiny 1 wrapper ... */`).

## 12. Fixtures

See [`fixtures/README.md`](fixtures/README.md).
