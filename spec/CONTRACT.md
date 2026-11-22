# SAShiny Contract Specification — Version 1

Status: **Draft 1 (phase 1)**. Spec release: **1.5**. This document is normative for both the R package and the Python library.
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

**Plain scalar typing.** R and Python MUST type every plain (unquoted) scalar the same way, so a
contract is valid in both languages or in neither (#155). The rule is the YAML 1.2 core schema,
restricted to the number forms that both languages' YAML parsers recognise:

| Type | Plain scalars (regular expressions match the whole scalar) |
|---|---|
| null | `~`, `null`, `Null`, `NULL`, or nothing |
| boolean | `true`, `True`, `TRUE`, `false`, `False`, `FALSE`; also `yes`, `no`, `on`, `off` in the same three spellings (kept from YAML 1.1 for compatibility; prefer `true`/`false`) |
| integer | `[-+]?(0\|[1-9][0-9]*)` or `0x[0-9a-fA-F]+` |
| float | `[-+]?(\.[0-9]+\|[0-9]+\.[0-9]*)([eE][-+][0-9]+)?`, `[-+]?\.(inf\|Inf\|INF)` or `\.(nan\|NaN\|NAN)` |
| string | everything else |

So `-.5`, `.5`, `1.` and `1.5e+3` are numbers, while `1_000`, `1,000`, `017` (leading zero), `1e3` and
`1.5e3` (an exponent needs a `.` before it and a sign), `0o17`, `0b101`, `1:30` and `y`/`n` are strings,
and a string where the schema wants a number is an `E000` error. Quote a value to make it a string.

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
Shiny ids. The default module `id` is derived from the program file name. Take the base name (after
the last `/` or `\`) without the `.sas` extension, lower-case it, remove combining marks (Unicode
general category `M`, that is `Mn`, `Mc` and `Me`, so `İ` lower-cases to `i`, not `i` plus a
combining dot), replace each character outside `[a-z0-9_]` with `_`, prefix `p_`
if it does not start with a letter, and truncate to 32 characters. Two programs that resolve to the
same module `id` (whether explicit or derived) MUST be rejected when the app is built.

The module reserves the internal ids `run`, `status`, `log`, `out_<output_id>` and `dl_<output_id>`
for its own controls and outputs, and `<dataset_id>__sample` for the sample toggle of a dataset input.
An input id that collides with any of these MUST be rejected when the app is built (or the module MUST
namespace its internal controls so no collision occurs).

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
| `plot` | ODS graphics of the run | `select` (1-based position; omit for all), `chart` (pairing, 8.6) |
| `chart` | dataset after the run, rendered client-side | `from` (`lib.member`), `columns`, `max_rows` (10000), `spec` or `render`, `sas_plot` (pairing, 8.6) |
| `html` | full ODS HTML listing | — |
| `log` | SAS log | `scope`: `program` (default) or `full` |
| `download` | file | `format`: `csv`, `xlsx`, `xpt`, `sas7bdat` (need `from`); `rtf`, `pdf` (ODS, no `from`); `filename` |

Every output has optional `label` and `help`.

A **paired output** shows both the original SAS graph and the SAShiny chart, with a toggle (8.6).
Either form declares one:
- a `chart` output with `sas_plot: <k>` (the 1-based ODS graph position, as in `plot.select`), or
- a `plot` output with a `chart` mapping. The mapping takes the `chart` output fields `from`
  (required), `columns`, `max_rows` and `spec`. A `plot` with a `chart` mapping MUST also have
  `select`, so that exactly one SAS graph is paired.

### 2.3 `run`

| Field | Default | Meaning |
|---|---|---|
| `entry` | `program` | `program`: submit the program text as-is. `macro`: submit the program text (which defines a macro), then call it. |
| `macro` | — | Macro to call when `entry: macro`. Each input's macro name is passed as a keyword parameter of the same name. |
| `timeout_seconds` | `300` | Wall-clock limit for the whole run. |
| `choices_ttl_seconds` | `3600` | How long `choices_from` lists are reused (§6.4); `0` disables the cache. |
| `cache` | `false` | Reuse the result of an identical earlier run (§6.11). Leave off for non-deterministic programs. |
| `cache_ttl_seconds` | `3600` | How long a cached result is reused (§6.11); `1`–`86400`. |
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
| `S003` | `min` MUST be ≤ `max` (numeric, date, daterange). A date/daterange `min` or `max` that is not a real calendar date (e.g. `2026-02-30`) is also `S003`. |
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
| `S017` | An input id MUST NOT collide with a generated module component id: `run`, `status`, `log`, any id starting with `out_` or `dl_`, or any id ending with `__sample`. (Output ids are always namespaced as `out_<id>`/`dl_<id>`, so they cannot collide.) |

### 3.3 Portable regex subset
`pattern` is matched against the **whole** value (implementations anchor it). It MUST be valid and
mean the same thing in ECMAScript, Python `re` and R's PCRE (`perl = TRUE`). Allowed: literals,
`.`, character classes `[...]` and `[^...]`, `\d \w \s \D \W \S`, quantifiers `* + ? {m} {m,} {m,n}`
(greedy only), groups `( )` and `(?: )`, alternation `|`, escapes of metacharacters.
Not allowed: look-around, back-references, named groups, inline flags, possessive or lazy quantifiers,
Unicode property classes, `^`/`$` anchors (outside a character class).

The shorthand classes `\d \w \s` (and their negations `\D \W \S`) use **ASCII** semantics: `\d` is
`[0-9]`, `\w` is `[A-Za-z0-9_]`, `\s` is `[ \t\n\r\f\v]`. This matches ECMAScript and R's PCRE
(`perl = TRUE`) defaults; Python implementations MUST compile the pattern with the `re.ASCII` flag so
all three agree. A `^` or `$` inside a character class is not an anchor: `[^x]` is a negated class and
`[$]` is a literal dollar sign, and both are allowed.

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
| `V009` | Date not a real calendar date, or outside `[min, max]`. A date with year `0000` is not a real calendar date and is `V009`. |
| `V010` | Daterange start after end. |
| `V011` | Value supplied for an id that is not an input of this contract. |
| `V012` | `integer: true` and value is not an integer. |
| `V013` | Rendered macro value longer than 32 000 bytes (UTF-8). |
| `V014` | Upload: extension not in `accept`, file larger than `max_size_mb`, unreadable, or missing a declared column. |

Normalisation happens **before** validation and is part of the contract:
- `text` values are trimmed of leading and trailing whitespace (Unicode `White_Space`). `choice` and
  `multichoice` values are **not** trimmed: a choice value is an opaque identifier and is matched
  against the declared choices exactly as submitted.
- `"today"` in `default`, `min` or `max` is resolved once, when the session starts, to the client's
  local date in the app's configured time zone (default: the server's time zone).
- An `optional` input with no value is **absent**. It is not an error and it renders as section 5.6.

For list-valued inputs (`multichoice`, `daterange`) the **shape check precedes the element check**:
a value that is not an array, or a `daterange` whose length is not exactly two, is `V002` regardless of
its elements. Only after the shape is correct are the elements type-checked (each must be a string,
else `V002`) and then validated (dates, choices, bounds). A `daterange` element that is not a string is
therefore `V002`, never `V009`, even when the other element is a malformed date.

A host that parses JSON values MUST NOT lose a control character before validation. In particular,
some runtimes (R character strings) cannot hold U+0000, and a JSON parser may silently truncate a
string at `\u0000`. Such a host MUST reject the value as `V007` instead, for example by mapping each
escaped U+0000 to another control character before parsing (R `sas_json_values()`; Python
`sashiny.json_values()` keeps U+0000 as is).

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

**Session setup.** Once per new SAS session, before any other submission, a live engine submits:

```sas
/* SAShiny 1 session */
options notes;
```

Some servers start sessions with `NONOTES` (SAS OnDemand for Academics does), which would remove the
`NOTE:` sentinels of 6.3 from the log and make every run look like an error.

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
[%<MACRO>(<NAME1>=<ARG1>, <NAME2>=<ARG2>, ...);] only if run.entry is macro; all input macro names, order of 5.7
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
  macros are included in the call only when declared. Each argument `<ARG>` is the rendered value with
  only the characters that would split the call or trigger macro execution masked, each one wrapped
  as `%nrstr(...)`. The value is scanned left to right:
  - A single-quoted string (`'...'`, with doubled quotes inside) is copied as written.
  - A double-quoted string (`"..."`, with doubled quotes inside) is copied with each `&` written
    `%nrstr(&)` and each `%` written `%nrstr(%%)`.
  - Outside strings, `,` `;` `&` are written `%nrstr(,)` `%nrstr(;)` `%nrstr(&)`, `%` is written
    `%nrstr(%%)`, an unmatched `'` or `"` is written `%nrstr(%')` or `%nrstr(%")`, and an unmatched
    `(` or `)` is written `%nrstr(%()` or `%nrstr(%))`. Parentheses are matched outside strings only.
  - Every other character is copied as written. An empty value gives an empty argument.

  For example, a `multichoice` with `separator: comma` that renders as `'A', 'B'` is passed as
  `'A'%nrstr(,) 'B'`, and `95` is passed as `95`. Masking the whole value (`%bquote(&NAME)`,
  `%superq(NAME)` or `%nrstr(<value>)`) is not used: SAS then treats the value as separate tokens, which
  breaks `WHERE` clauses and names built from it such as `l&level` (see §9).
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

**Caching.** The choices of a contract are loaded once per app (or per engine, outside an app) and
cached, keyed by contract SHA-256, for `run.choices_ttl_seconds` (integer 0–86400, default 3600; 0
means never reuse). The cache is cleared when the SAS session or worker is replaced. In a Shiny
module:
- the load runs in the background;
- each input whose choices are not loaded yet shows "Loading choices…";
- the inputs fill when the load finishes;
- a failure is shown in the status card (#68).

A run uses fresh cached choices. Otherwise, it loads them inside the run, which is already off the
event loop (§6.5), so validation always sees the choices.

### 6.5 Run status
The engine reads the log of the main submission:

| Status | Condition |
|---|---|
| `error` | `SASHINY-END` sentinel missing (program ended the session, unbalanced quotes, timeout), or `syscc` > 4, or any log line starting with `ERROR` |
| `warning` | otherwise, any log line starting with `WARNING`, or `syscc` = 4 |
| `success` | otherwise |

A timeout MUST abort the SAS session. The pool MUST then discard and replace that session.

*In-session exception (PROC PYTHON, Python only).* An in-session engine (§6.6) runs inside the SAS job
that started it and cannot abort its own parent session. When `timeout_seconds` passes, it MUST stop
waiting and return an `error` result with `metadata.engine_error` starting with
`run exceeded timeout_seconds`, and it MUST refuse every later run on that engine with an error
result. Ending the SAS job is left to the scheduler that started it. There is no pool for
in-session engines: one SAS job is one session and runs one contract at a time.

**Session lifetime.**
- An engine owns one SAS session and reuses it across runs. Each run resets WORK (§6.2). The session
  is replaced only after an engine error or a timeout, and the replacement starts lazily, on the next
  run.
- A pool is `N` persistent workers. Each worker owns one SAS session for its lifetime; a run uses a
  free worker; a timeout or engine error discards that worker.
- In a Shiny app, a run never blocks the event loop. Other sessions in the same process keep
  updating while a run is in flight, for single engines and pools. Ending the browser session cancels
  its in-flight run.

These rules are observable with the mock engine and a fake session (the session object is created
once per worker), so they are tested without SAS.

When every pooled session is busy, a pool MUST wait for a free session up to a configurable
`acquire_timeout` (default 30 seconds) rather than failing immediately. If no session becomes free
within the timeout, the run returns an error `Result` with `metadata.engine_error` set to
`pool exhausted: all N sessions busy` (it MUST NOT raise). A run on a closed pool returns an error
`Result` with `metadata.engine_error` equal to `pool closed`.

One engine runs one contract at a time on its one SAS session. A run that starts while another run
on the same engine is in progress waits up to 30 seconds for it to finish; if it does not, the run
returns an error `Result` with `metadata.engine_error` equal to `engine busy: another run is in
progress`. `metadata.engine_error` holds the failure message only, never a language-specific
exception class name.

### 6.6 Supported backends and licence acknowledgement

A run that users can reach through the public API MUST be executed by a live, licensed SAS system.
Exactly three backends are supported through saspy, plus one in-session backend (Python only):

| Backend | saspy access method | Configuration that identifies it |
|---|---|---|
| SAS OnDemand for Academics (ODA) | IOM | `iomhost` is a list of `*.oda.sas.com` hosts, `authkey: oda` |
| SAS Viya | HTTP | `url` starting with `https://` (or `http://`) |
| SAS 9.4 | IOM or SSH | IOM: `iomhost` (one host) and `iomport`; SSH: `saspath` and `host` |
| In-session (PROC PYTHON) | none: the `SAS` callback object of PROC PYTHON | `connect_in_session(SAS, ...)` inside a SAS Viya or SAS 9.4M9+ job |

**In-session backend.** `sashiny.connect_in_session(SAS, license_ack=..., own_session=False)` returns
an engine that submits through the `SAS` object PROC PYTHON injects into its Python session. It runs
in batch only (no Shiny server inside PROC PYTHON). Each main submission is wrapped in
`PROC PRINTTO LOG=` and `ODS HTML5 FILE=` files in the WORK directory, which the engine reads back as
the log and the listing; the run status (§6.5) is parsed from that log exactly as for saspy. Downloads
are read from the WORK directory on disk. Because the run shares the user's SAS session, the §6.2 reset
(which empties WORK and deletes macro variables) is allowed only with `own_session = True`, which
confirms that the SAS job exists only for this run; a contract with `reset_work: true` (the default) on
an engine without `own_session = True` returns an error result and submits nothing. SAShiny cannot fully
verify that the object is a real PROC PYTHON callback, so the licence acknowledgement applies as for
every backend. R has no in-session backend (PROC R is a follow-up).

Rules:
- An engine configuration (a saspy configuration mapping) that matches none of the rows is rejected when the engine is
  created, with an error naming the three supported backends. In particular, local Windows COM
  (`provider`), local STDIO (`saspath` without `host`) and unknown methods are rejected. A path to an
  existing saspy configuration file is accepted as is. SAShiny cannot inspect it, and the user is
  responsible for it pointing at one of the supported backends.
- The user is responsible for holding a valid SAS licence (or ODA terms of use) for the backend.
  SAShiny cannot verify a licence. Instead, a live engine MUST refuse to start a SAS session unless the
  user has explicitly acknowledged this responsibility. An acknowledgement is one of: an explicit
  `license_ack = TRUE`/`license_ack=True` argument, the R option `SAShiny.license_ack = TRUE`, or the
  environment variable `SASHINY_LICENSE_ACK` set to `true` or `1` (case-insensitive; for deployed apps).
  Without an acknowledgement the run returns an error `Result` whose `metadata.engine_error` starts with
  `SAS licence not acknowledged`. Building an engine without an acknowledgement is allowed, so
  configuration can be inspected offline.
- SAS logs come only from SAS. The public API MUST NOT offer a way to supply a log, a result or a
  recording that did not come from a live SAS run, and live engines MUST NOT write recordings.
- The offline mock engine (8.3) is an internal test fixture. It is not part of the public API.

### 6.7 Publishing to Posit Connect

Both languages provide a `publish` helper that deploys an app directory to Posit Connect. It uses the
language's official Connect client (`rsconnect` for R, `rsconnect-python` for Python). Rules:

- **Authentication** is either a Connect account the user has already registered with the client, or the
  environment variables `CONNECT_SERVER` and `CONNECT_API_KEY`. An API key is never written to the bundle,
  the contract or a log.
- **Bundle contents.** The bundle MUST NOT contain credential files. A file named `.authinfo`,
  `_authinfo`, `.netrc`, `_netrc`, `.Renviron` or `.env`, or matching `*.pem` or `*.key`, is always
  excluded, and the helper reports which files it excluded.
- **SAS credentials on Connect** come from the Connect content's environment variables
  `SASHINY_SAS_USER` and `SASHINY_SAS_PASSWORD`, or from an `~/.authinfo` the server administrator
  manages for the content's run-as user. When both variables are set, a live engine passes them to
  saspy as session keyword arguments: `omruser`/`omrpw` for IOM, `user`/`pw` for HTTP (Viya). They are
  never written to a file. The authinfo check is skipped in that case. SSH uses key-based login and
  ignores them. The helper can set these variables on the content, but their values are sent only to Connect.
- **Licence.** Publishing sets `SASHINY_LICENSE_ACK=true` on the content only when the publisher has
  acknowledged the licence (6.6).
- The in-app "Publish" control is opt-in. It MUST be hidden when the app itself runs on Posit Connect
  (environment variable `RSTUDIO_PRODUCT` equal to `CONNECT`, or `CONNECT_SERVER_URL`/`CONNECT_CONTENT_GUID` set).

### 6.8 Deployment targets

A **deployment target** turns an app directory into deployment artifacts for one hosting platform. Both
languages provide the same targets through `sas_deploy()` (R) and `sashiny.deploy.deploy()` (Python), and
list them with `sas_deploy_targets()` / `sashiny.deploy.targets()`.

**Target ids:** `container`, `azure_container_apps`, `aws_ecs_express`, `snowflake_spcs`,
`posit_snowflake`, `streamlit_snowflake`, `databricks_apps`.

**Phases.**
- `generate` writes artifacts to an output directory. It MUST NOT touch the network or run any external
  program. Its output is fully determined by the app directory, the profile and the options.
- `apply` is a separate, explicit step (`apply = TRUE`). It runs the platform CLI through a command
  runner that tests can replace. It MUST NOT print secret values.
- `doctor` checks local prerequisites (CLI on `PATH`, login state, required environment variables). It
  reports names and exit statuses only, never values.

**Connection profile.** A target receives a SAS connection profile with these fields:

| Field | Values | Meaning |
|---|---|---|
| `name` | string | Profile id (for messages) |
| `method` | `iom`, `http`, `ssh` | saspy access method |
| `oda_region` | `us1`, `us2`, `eu1`, `ap1`, `ap2` | ODA only. Selects the ODA IOM hosts of §6.6 |
| `iomhost`, `iomport` | host, port (default 8591) | SAS 9.4 IOM |
| `url` | `https://...` or `http://...` | SAS Viya |
| `host`, `saspath` | host, path of the SAS executable | SAS 9.4 SSH |
| `requires_vpn` | `true` / `false` (default `false`) | The SAS host is reachable only over a private network |

Other fields (for example `label`, `authkey`, `encoding`) are ignored. A profile is invalid, with an
error starting with `profile <name>: `, when:
- `method` is missing or not one of the three values;
- `oda_region` is given with a method other than `iom`, or is not a known region;
- an `iom` profile has neither `oda_region` nor `iomhost`;
- `iomport` is not an integer from 1 to 65535;
- an `http` profile has no `url` starting with `https://` or `http://`;
- an `ssh` profile lacks `host` or `saspath`;
- `requires_vpn` is not a boolean;
- a host, URL or path contains whitespace, a control character, `"`, `'`, `\`, `$` or `` ` ``
  (`saspath` may contain spaces). Such values could not be written safely into generated files.

A profile with `oda_region` is ODA. Its **kind** is `oda`; other `iom` and `ssh` profiles are `sas94`,
and `http` profiles are `viya`. Its **egress endpoints**, the `host:port` pairs the app must reach,
are derived as follows:

| Profile | Endpoints |
|---|---|
| ODA (`oda_region`) | each ODA host of the region, port 8591, in the order of §6.6 |
| `iom` | `iomhost:iomport` |
| `http` | the URL host, with the URL port, or 443 for `https` and 80 for `http` |
| `ssh` | `host:22` |

**Java.** A profile with method `iom` (including ODA) needs Java 17 in the runtime. A target whose
runtime cannot provide Java MUST reject `iom` profiles with an error naming the target and the profile.

**Private networks.** When `requires_vpn` is `true`, a target MUST fail unless the caller passes the
target's private-network option. The error starts with `profile <name> requires a private network`.
For `container` that option is `private_network = TRUE`: the caller confirms the host the image runs
on can reach the SAS host. Platform targets use their own option, for example a subnet id, or a
confirmation that PrivateLink is configured.

**Errors.** `generate` checks, in this order:
1. the target id, with an error starting with `unknown deployment target`;
2. the licence;
3. the profile;
4. the private network;
5. the options, for example `port must be an integer from 1 to 65535`;
6. the language.

Errors never include option or environment values that could be secrets.

**Runtime environment.** Every target configures two kinds of environment variables in the deployed
app. The first are plain settings, in this order:
1. `SASHINY_LICENSE_ACK=true`. `generate` MUST fail unless the deployer passes `license_ack = TRUE`,
   with an error starting with `deploying requires license_ack = TRUE`.
2. `SASHINY_PROFILE`: the profile kind (`oda`, `viya` or `sas94`).
3. The connection settings of the kind:

| Kind | Variables, in order |
|---|---|
| `oda` | `SASHINY_ODA_REGION` |
| `viya` | `SASHINY_VIYA_URL` |
| `sas94` (`iom`) | `SASHINY_SAS94_HOST`, `SASHINY_SAS94_PORT` |
| `sas94` (`ssh`) | `SASHINY_SAS94_HOST`, `SASHINY_SAS94_SASPATH` |

The second are secrets, which appear only by name: `SASHINY_SAS_USER` and `SASHINY_SAS_PASSWORD`,
for `iom` and `http` profiles (§6.7). Their values come from the platform's secret store. SSH uses
key-based login and has no secrets.

A deployed app builds its engine from these variables with `sas_connect_env()` (R) or
`sashiny.connect_from_env()` (Python). These read the variables above and call `sas_connect()` /
`sashiny.connect()` with them. The licence is acknowledged through `SASHINY_LICENSE_ACK` (§6.6).

**Bundle.** The files deployed from the app directory are the §6.7 bundle. Credential files are always
excluded, and the excluded names are reported. Files under a directory named `.git`, `.Rproj.user`,
`.venv`, `__pycache__`, `rsconnect` or `rsconnect-python`, at any depth, are skipped and not reported.
Paths are POSIX paths relative to the app directory, sorted by their UTF-8 bytes. The same rules apply
to `publish` (§6.7). Generated artifacts MUST NOT contain secret values, credentials or API keys.

**Language.** An app directory with `app.py` is a `python` app; one with `app.R` is an `r` app. With
both, the caller must pass the language. With neither, the caller must pass the language, and the
target adds a **generated app** to the bundle that serves every `*.sashiny.yml` contract in the
directory on a session pool built from the environment (`max_size = 2`). The error for a missing
language starts with `cannot detect the app language`. The generated app files are:

`app.py`:
```python
# Generated by SAShiny (CONTRACT.md 6.8). Serves every contract in this folder.
from pathlib import Path

import sashiny

HERE = Path(__file__).resolve().parent
CONTRACTS = sorted(HERE.rglob("*.sashiny.yml"))
app = sashiny.app(CONTRACTS, sashiny.Pool(sashiny.connect_from_env, max_size=2), title="SAShiny")
```

`app.R`:
```r
# Generated by SAShiny (CONTRACT.md 6.8). Serves every contract in this folder.
library(SAShiny)

contracts <- sort(list.files(".", pattern = "[.]sashiny[.]yml$", recursive = TRUE, full.names = TRUE))
sas_app(contracts, sas_pool(sas_connect_env, max_size = 2L), title = "SAShiny")
```

**Output layout.** `generate` writes into the output directory, which it creates and which MUST be
empty or absent:
- `bundle/`: the bundle files, plus the generated app when there is one;
- the target's own artifacts (for `container`, the `Dockerfile`).

The result lists the written files (POSIX paths relative to the output directory, sorted by UTF-8
bytes) and the excluded credential files. It also lists the plain environment variables in order,
the secret names, and the egress endpoints. Generated text files use LF line endings and end with a
newline.

**Web serving.** Shiny needs WebSockets and session affinity. Every target that fronts the app with a
load balancer MUST enable both, or document why the platform provides them by default.

**Container image (`container` target).** The `container` target writes a `Dockerfile` (next to
`bundle/`) for one app, in language `r` or `python`, and a `.dockerignore`. The other container-based
targets build on it. The image installs the SAShiny release equal to the generating package's
version (`<VERSION>`): the PyPI release for Python, and the git tag `r-v<VERSION>` of
`procogia/SAShiny` for R, which every R release creates. Options: `port` (integer 1–65535, default
8000) and `language`.

The image MUST:
- run as a non-root user;
- listen on `port`;
- declare a `HEALTHCHECK` on `/`;
- install Java 17 only when the profile's method is `iom`;
- copy only `bundle/`;
- contain no environment values except `PORT`;
- fail to build when a package it needs is not installed (R's `install.packages()` only warns).

The deployment platform sets the runtime environment above.

The Python image is based on Debian bookworm, which ships Java 17 (later Debian releases do not).
The R image installs R packages from its base image's repository, which serves Linux binaries, and
installs `libpython3-dev`, which reticulate needs to load Python. Both images target `linux/amd64`:
build with `docker build --platform linux/amd64` on an ARM machine, because some Python packages
have no ARM Linux wheels.

`Dockerfile`, language `python`. The `[...]` lines are present only for `iom` profiles:
```dockerfile
# Generated by SAShiny <VERSION> (CONTRACT.md 6.8). Do not edit by hand.
FROM python:3.12-slim-bookworm
[RUN apt-get update \]
[ && apt-get install -y --no-install-recommends openjdk-17-jre-headless \]
[ && rm -rf /var/lib/apt/lists/*]
RUN pip install --no-cache-dir "sashiny[shiny,saspy,upload,plotnine]==<VERSION>"
RUN useradd --create-home --uid 10001 sashiny
WORKDIR /app
COPY --chown=sashiny:sashiny bundle/ /app/
USER sashiny
ENV PORT=<PORT>
EXPOSE <PORT>
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:<PORT>/', timeout=4)"
CMD ["sh", "-c", "exec shiny run app.py --host 0.0.0.0 --port \"$PORT\""]
```

`Dockerfile`, language `r`. The `openjdk-17-jre-headless \` line is present only for `iom` profiles:
```dockerfile
# Generated by SAShiny <VERSION> (CONTRACT.md 6.8). Do not edit by hand.
FROM rocker/r-ver:4.5.2
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      [openjdk-17-jre-headless \]
      python3 python3-venv libpython3-dev curl libcurl4-openssl-dev libssl-dev \
 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/saspy \
 && /opt/saspy/bin/pip install --no-cache-dir "saspy>=5.100" "pandas>=2.0"
ENV RETICULATE_PYTHON=/opt/saspy/bin/python
RUN Rscript -e 'pkgs <- c("remotes", "shiny", "bslib", "callr", "later", "promises", "reticulate", "ggplot2"); install.packages(pkgs); stopifnot(all(vapply(pkgs, requireNamespace, TRUE, quietly = TRUE)), packageVersion("reticulate") >= "1.45.0")' \
 && Rscript -e 'remotes::install_github("procogia/SAShiny/R@r-v<VERSION>", upgrade = "never"); stopifnot(requireNamespace("SAShiny", quietly = TRUE))'
RUN useradd --create-home --uid 10001 sashiny
WORKDIR /app
COPY --chown=sashiny:sashiny bundle/ /app/
USER sashiny
ENV PORT=<PORT>
EXPOSE <PORT>
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:<PORT>/" > /dev/null || exit 1
CMD ["sh", "-c", "exec Rscript -e \"shiny::runApp('/app', host = '0.0.0.0', port = as.integer(Sys.getenv('PORT')))\""]
```

`.dockerignore` (both languages):
```
*
!bundle/
```

The exact bytes are fixed by `spec/fixtures/deploy/`, with `<VERSION>` replaced by `0.0.0` in the
fixtures. A fixture case passes `version = "0.0.0"`, which `generate` accepts for testing only.

#### 6.8.1 `azure_container_apps`

The target deploys the `container` image to Azure Container Apps
([Bicep reference](https://learn.microsoft.com/en-us/azure/templates/microsoft.app/containerapps),
[sticky sessions](https://learn.microsoft.com/en-us/azure/container-apps/sticky-sessions)). It writes the
`container` artifacts, plus `infra/main.bicep`, `infra/main.parameters.json` and `deploy-azure.md`.

**Options:**

| Option | Default | Meaning |
|---|---|---|
| `port` | 8000 | as for `container` |
| `app_name` | `sashiny-app` | Container App name: 2–32 characters, lowercase letters, digits and `-`, starting with a letter |
| `max_replicas` | 1 | 1–30 |
| `infrastructure_subnet_id` | none | Subnet resource id for VNet integration; the private-network option of this target |

The template:
- uses API version `2025-07-01`;
- sets external ingress on the port, with transport `auto` (WebSockets) and `stickySessions.affinity: 'sticky'`;
- sets single-revision mode and min replicas 1, with 2 vCPU and 4 GiB per replica;
- pulls the image from an existing Azure Container Registry with a user-assigned managed identity
  that has the `AcrPull` role;
- adds a Log Analytics workspace.

The plain environment of §6.8 is written as container `env` values. Each secret name maps to a
Container App secret (lower case, `_` becomes `-`, for example `SASHINY_SAS_USER` →
`sashiny-sas-user`) that references a Key Vault secret URI. The URI is a template parameter with no
default (`sasUserSecretUri`, `sasPasswordSecretUri`), and the managed identity reads it. With
`infrastructure_subnet_id`, the environment gets `vnetConfiguration.infrastructureSubnetId`.

For an SSH profile there are no secrets, so the `secrets` block and the secret URI parameters are
left out. `main.parameters.json` is a standard deployment parameters file that sets only the
non-secret parameters the options determine: `appName`, `port`, `maxReplicas` and, when given,
`infrastructureSubnetId`. The deployer supplies the rest on the command line: `acrName`, `imageTag`
and the secret URIs. `deploy-azure.md` lists the exact commands with placeholders. The exact bytes are
fixed by `spec/fixtures/deploy/azure_*`.

`apply` runs, in order:
1. `az acr build --registry <acr> --image <app_name>:<image_tag> <out_dir>`
2. `az deployment group create --resource-group <rg> --template-file <out_dir>/infra/main.bicep
   --parameters @<out_dir>/infra/main.parameters.json acrName=<acr> imageTag=<image_tag> ...`

The apply options are `resource_group`, `acr_name`, `image_tag` (default `latest`) and the two
secret URIs. `doctor` reports `az` missing from `PATH`, or `az account show` failing (not logged in).

#### 6.8.2 `aws_ecs_express`

The target deploys the `container` image to Amazon ECS on Fargate behind an Application Load
Balancer. [ECS Express Mode](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/express-service-overview.html)
([`AWS::ECS::ExpressGatewayService`](https://docs.aws.amazon.com/AWSCloudFormation/latest/TemplateReference/aws-resource-ecs-expressgatewayservice.html))
does not expose target-group stickiness or the load balancer idle timeout. Shiny needs both, so the
template declares the standard ECS and Elastic Load Balancing resources instead, and the generated
guide says so. The target writes the `container` artifacts, plus `infra/template.yaml`
(CloudFormation) and `deploy-aws.md`.

**Options:**

| Option | Default | Meaning |
|---|---|---|
| `port` | 8000 | as for `container` |
| `app_name` | `sashiny-app` | as for `azure_container_apps`; it names the cluster, service, load balancer and target group |
| `desired_count` | 1 | Number of tasks, 1–10 |
| `private_network` | false | `true` confirms that the private subnets route to the SAS network (VPN or Transit Gateway); the private-network option of this target |

The template:
- declares an internet-facing ALB in `PublicSubnetIds`, with an HTTPS listener using `CertificateArn`
  and the attribute `idle_timeout.timeout_seconds` set to `3600` (WebSockets);
- declares a target group of type `ip` with a health check on `/` and `lb_cookie` stickiness for
  86400 s;
- declares a Fargate service (2 vCPU / 4 GiB, `X86_64`, container user `10001`) in
  `PrivateSubnetIds` without public IP addresses;
- declares a log group, a task role, and an execution role. When the profile has secrets, the
  execution role may read only the two secret ARNs.

The service security group allows inbound traffic on the port from the load balancer only. Outbound,
it allows TCP 443 to `0.0.0.0/0` (AWS APIs, and the SAS endpoints on port 443), and each other
distinct SAS port to the parameter `SasEgressCidr` (default `0.0.0.0/0`), in ascending port order.
`SasEgressCidr` is declared only when there is such a port. The load balancer accepts TCP 443 from
anywhere. With `private_network: true`, `deploy-aws.md` adds a paragraph on routing the private
subnets to the SAS network.

The plain environment of §6.8 is written as the container's `Environment`, with values in single
quotes. The secrets are written as `Secrets` whose `ValueFrom` is a parameter holding a Secrets
Manager ARN (`SasUserSecretArn`, `SasPasswordSecretArn`), with no default. For an SSH profile, the
secret parameters, the execution-role policy and `Secrets` are left out. The exact bytes are fixed
by `spec/fixtures/deploy/aws_*`.

`apply` runs, in order. The deployer logs Docker in to ECR first, as the guide shows:
1. `docker build --platform linux/amd64 -t <image_uri> <out_dir>`
2. `docker push <image_uri>`
3. `aws cloudformation deploy --stack-name <stack_name> --template-file <out_dir>/infra/template.yaml
   --capabilities CAPABILITY_IAM --parameter-overrides ImageUri=<image_uri> VpcId=<vpc_id>
   PublicSubnetIds=<ids> PrivateSubnetIds=<ids> CertificateArn=<arn> [SasUserSecretArn=<arn>
   SasPasswordSecretArn=<arn>]`

The apply options are:
- `image_uri`, `vpc_id`, `public_subnet_ids`, `private_subnet_ids` and `certificate_arn`, all
  required;
- `stack_name`, default `app_name`;
- for profiles with secrets, `sas_user_secret_arn` and `sas_password_secret_arn`.

Subnet ids may be a list, joined with `,`. `doctor` reports, in order: `aws` missing from `PATH`,
`aws sts get-caller-identity` failing (no credentials), and `docker` missing from `PATH`.

#### 6.8.3 `snowflake_spcs`

The target runs the `container` image as a Snowpark Container Services service
([specification reference](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/specification-reference),
[network communications](https://docs.snowflake.com/en/developer-guide/snowpark-container-services/service-network-communications)).
A public endpoint is reached through Snowflake sign-in. Ingress supports WebSockets and closes a
connection after 90 s without traffic; Shiny's WebSocket heartbeat keeps it open. Snowflake does not
document session affinity between service instances, so the default is one instance. When
`instances` is more than 1, the guide warns that sessions may move between instances.

The target writes the `container` artifacts plus these files:
- `spcs/service-spec.yaml`: the service specification;
- `spcs/setup.sql`: the database, schema, image repository, compute pool, egress network rule and
  external access integration;
- `spcs/service.sql`: the service, the optional endpoint grant and `SHOW ENDPOINTS`;
- `spcs/secret.sql`, only for profiles with secrets: the credentials secret, with placeholders
  only;
- `deploy-snowflake-spcs.md`: the deployment guide.

Images are built for `linux/amd64`.

**Options.** Identifiers are 1–63 characters: uppercase letters, digits and `_`, starting with a
letter.

| Option | Default | Meaning |
|---|---|---|
| `port` | 8000 | as for `container` |
| `service_name` | `SASHINY_APP` | Service name (identifier) |
| `database` | `SASHINY_DB` | Database (identifier) |
| `schema` | `APP` | Schema (identifier) |
| `compute_pool` | `SASHINY_POOL` | Compute pool (identifier) |
| `instance_family` | `CPU_X64_S` | Compute pool instance family (identifier) |
| `instances` | 1 | Service instances and pool nodes, 1–10 |
| `public` | true | Whether the endpoint is public |
| `grant_role` | none | Role (identifier) granted the service role `<service>!ALL_ENDPOINTS_USAGE` |
| `private_connectivity` | false | `true` confirms private connectivity to SAS (for example AWS PrivateLink or Azure Private Link) is configured; the private-network option of this target |

**Derived names.**
- The image repository is `SASHINY_REPO`.
- The image is `/<database>/<schema>/sashiny_repo/<image>:latest`, in lower case, where `<image>` is
  the service name in lower case with `_` replaced by `-`.
- The secret, network rule and integration are `<service>_SAS_CREDENTIALS`, `<service>_SAS_EGRESS`
  and `<service>_SAS_ACCESS`.

The specification has one container `app` and one endpoint `app` on the port:
- The plain environment of §6.8 is written as `env`, with values in single quotes.
- Each secret is read from the credentials secret (`TYPE = PASSWORD`) with `secretKeyRef`:
  `username` for `SASHINY_SAS_USER` and `password` for `SASHINY_SAS_PASSWORD`.
- The readiness probe is on `/`.

The network rule is `TYPE = HOST_PORT`, `MODE = EGRESS`, with the profile's endpoints in order.
`service.sql` repeats the specification, without its comment line, inside
`FROM SPECIFICATION $$ ... $$`. The exact bytes are fixed by `spec/fixtures/deploy/snowflake_*`.

`apply` runs, in order. Each `snow` command gets `--connection <connection>` when the option is
given:
1. `snow sql -f <out_dir>/spcs/setup.sql`
2. `snow spcs image-registry login`
3. `docker build --platform linux/amd64 -t <repository_url>/<image>:latest <out_dir>`
4. `docker push <repository_url>/<image>:latest`
5. `snow sql -f <out_dir>/spcs/service.sql`

The apply options are `repository_url` (required; from `SHOW IMAGE REPOSITORIES`) and
`connection`. `apply` does not run `secret.sql`; the deployer runs it by hand first, as the guide
shows. `doctor` reports, in order: `snow` missing from `PATH`, `snow connection test` failing (no
working connection), and `docker` missing from `PATH`.

#### 6.8.4 `posit_snowflake`

The target publishes the app to Posit Connect inside the Posit Team Native App
([egress](https://docs.posit.co/partnerships/snowflake/posit-team/networking/egress.html),
[publishing from outside Snowflake](https://docs.posit.co/partnerships/snowflake/posit-team/connect/publish-outside-snowflake.html)).
Posit manages the runtime, and the app is ordinary Connect content. The target reuses the §6.7
publisher and writes no container. It writes `bundle/`, `snowflake/egress.sql` and
`deploy-posit-snowflake.md`.

The Native App's containers reach SAS only through an external access integration. Its Connect
integration is `<application>_CONNECT_EGRESS_EXTERNAL_ACCESS`, which allows the rule
`<application>_APP_DATA.CONFIGURATION.<application>_CONNECT_EGRESS_NETWORK_RULE`. `egress.sql`:
- describes the integration;
- creates a network rule in `<application>_APP_DATA.CONFIGURATION` for the profile's endpoints;
- sets the integration's allowed rules to the Connect rule plus the new rule. `SET` replaces the
  list, so the file says to keep any other rule the description shows.

There are two kinds of rule:
- Public: one rule `<application>_SASHINY_SAS_EGRESS`, `TYPE = HOST_PORT`, with all endpoints.
- With `private_connectivity`: a private rule allows one host, so there is one rule per endpoint,
  `<application>_SASHINY_SAS_PRIVATE_<n>` (`n` from 1), `TYPE = PRIVATE_HOST_PORT`. Each needs a
  provisioned private endpoint first.

**Options.**

| Option | Default | Meaning |
|---|---|---|
| `application` | `POSIT_TEAM` | The installed application name (identifier, as in §6.8.3) |
| `private_connectivity` | false | as for `snowflake_spcs`; the private-network option of this target |

**Guide.** The guide shows server registration for the app's language only: `rsconnect add ...
--snowflake-connection-name` for Python, or `rsconnect::addServer()` and
`rsconnect::connectSPCSUser()` for R. For `iom` profiles it notes that Java 17 must be available in
the Connect runtime image; the target does not verify this. The exact bytes are fixed by
`spec/fixtures/deploy/posit_*`.

**Apply.** `apply` publishes `<out_dir>/bundle` with the §6.7 publisher (`publish` / `sas_publish`):
- `title` goes to the publisher.
- The server is the `server` option (a registered server nickname). Without it, `CONNECT_SERVER` and
  `CONNECT_API_KEY` must both be set; otherwise `apply` fails with
  `apply needs the option server or the environment variables CONNECT_SERVER and CONNECT_API_KEY`.
- The plain environment of §6.8 is set in the process only for the publish call, and its names are
  sent with `--environment` / `envVars`, so Connect stores the values.
- `sas_credentials` is `"env"` when the profile has secrets, and `"server"` for SSH.
- Each package publishes apps in its own language. Applying an R app from Python fails with
  `apply for an R app must run in R (SAShiny::sas_deploy)`. Applying a Python app from R fails with
  `apply for a Python app must run in Python (sashiny.deploy.deploy)`.

`doctor` reports, in order:
1. the Connect publisher missing (`rsconnect-python` or the R package 'rsconnect');
2. `CONNECT_SERVER` or `CONNECT_API_KEY` unset (names only).

#### 6.8.5 `streamlit_snowflake` (Python only)

The target runs the §6.9 Streamlit front end as a Streamlit in Snowflake app on a container runtime
([CREATE STREAMLIT](https://docs.snowflake.com/en/sql-reference/sql/create-streamlit),
[runtime environments](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/runtime-environments),
[dependencies](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/dependency-management),
[secrets](https://docs.snowflake.com/en/developer-guide/streamlit/app-development/secrets-and-configuration)).

The container runtime is a managed Python image. Dependencies come only from `pyproject.toml` or
`requirements.txt`, installed with `uv`, so no system package can be installed: there is no Java and
no `ssh` client. The target therefore:
- needs no Java runtime. An `iom` profile fails with the §6.8 Java error (`target
  streamlit_snowflake cannot provide Java 17, ...`).
- accepts only `http` (Viya) profiles. An `ssh` profile fails with `target streamlit_snowflake
  supports only http (Viya) profiles`.
- accepts language `python` only. An R app fails with `target streamlit_snowflake does not support
  language r`; R users choose a container-based target.

The bundle is the app directory. Its `app.py`, if any, is copied but not used. The target writes:
- `bundle/streamlit_app.py`;
- `bundle/pyproject.toml`;
- `snowflake/setup.sql`;
- `snowflake/secret.sql`;
- `snowflake/streamlit.sql`;
- `deploy-streamlit-snowflake.md`.

**Options.** Identifiers are as in §6.8.3.

| Option | Default | Meaning |
|---|---|---|
| `app_name` | `SASHINY_STREAMLIT` | Streamlit object name (identifier) |
| `database` | `SASHINY_DB` | Database (identifier) |
| `schema` | `APP` | Schema (identifier) |
| `compute_pool` | `SASHINY_STREAMLIT_POOL` | Compute pool (identifier) |
| `warehouse` | `SASHINY_WH` | Query warehouse (identifier) |
| `title` | `SAShiny` | App title: 1–100 characters without `'`, `"`, `\` or control characters |
| `private_connectivity` | false | as for `snowflake_spcs` |

`streamlit_app.py` serves every contract in the bundle with `sashiny.streamlit_app`. A Streamlit
object has no settable environment, so the file sets the plain (non-secret) variables of §6.8
itself, one `os.environ.setdefault` line per variable, in order. The values are checked by §6.8 (no
quotes, backslashes or control characters), so they are safe in a Python string literal.
```python
# Generated by SAShiny <VERSION> (CONTRACT.md 6.8.5). Serves every contract in this folder.
import os
from pathlib import Path

import sashiny
from sashiny.streamlit_app import streamlit_app

os.environ.setdefault("<NAME>", "<value>")
HERE = Path(__file__).resolve().parent
streamlit_app(sorted(HERE.rglob("*.sashiny.yml")), sashiny.connect_from_env, title="<title>")
```

`pyproject.toml` declares the project `sashiny-streamlit-app` (version `0.0.0`, Python `>=3.11`)
with one dependency, `sashiny[saspy,upload,streamlit]==<VERSION>`. It is installed from PyPI through
the Snowflake artifact repository `snowflake.snowpark.pypi_shared_repository`.

The SQL files run in this order: `setup.sql`, then `secret.sql`, then `streamlit.sql`, which needs
the secret.

`setup.sql` creates, with `IF NOT EXISTS`:
- the database, the schema and the stage `SASHINY_STAGE`;
- the warehouse (`XSMALL`, auto-suspend 60 s);
- the compute pool (`CPU_X64_XS`, 1 node).

It then creates the egress network rule `<app>_SAS_EGRESS` (`HOST_PORT`). With
`private_connectivity`, it instead creates one `PRIVATE_HOST_PORT` rule `<app>_SAS_PRIVATE_<n>` per
endpoint.

`secret.sql` is as in §6.8.3, with the object `<app>_SAS_CREDENTIALS`.

`streamlit.sql` creates the external access integration `<app>_SAS_ACCESS`, which allows the rules
and the secret. It then runs `CREATE STREAMLIT IF NOT EXISTS <app>` with:
- `FROM '@<database>.<schema>.SASHINY_STAGE/app'`, `MAIN_FILE = 'streamlit_app.py'`;
- `RUNTIME_NAME = 'SYSTEM$ST_CONTAINER_RUNTIME_PY3_11'`;
- the compute pool, query warehouse and `TITLE`;
- `ARTIFACT_REPOSITORIES = (snowflake.snowpark.pypi_shared_repository)`;
- the integration;
- `SECRETS = ('sashiny_sas' = <secret>)`.

It ends with `ALTER STREAMLIT <app> ADD LIVE VERSION FROM LAST`. Rules and the secret are fully
qualified with `<database>.<schema>`.

The runtime exposes the secret as `sashiny_sas_USERNAME` and `sashiny_sas_PASSWORD`.
`streamlit_app` copies them to `SASHINY_SAS_USER` and `SASHINY_SAS_PASSWORD` when those are
unset.

`apply` runs, in order, each `snow` command with `--connection` as in §6.8.3:
1. `snow sql -f <out_dir>/snowflake/setup.sql`
2. `snow stage copy <out_dir>/bundle @<database>.<schema>.SASHINY_STAGE/app --recursive --overwrite`
3. `snow sql -f <out_dir>/snowflake/streamlit.sql`

`apply` does not run `secret.sql`. The deployer runs `setup.sql` and then `secret.sql` by hand
first, as the guide shows; `setup.sql` is idempotent, so `apply` may run it again. `doctor` reports
`snow` missing from `PATH`, or `snow connection test` failing. The exact bytes are fixed by
`spec/fixtures/deploy/streamlit_*`.

#### 6.8.6 `databricks_apps` (Python only)

The target runs a Shiny for Python app as a Databricks App
([app.yaml](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime),
[environment](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/system-env),
[dependencies](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/dependencies),
[secrets](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/secrets),
[deploy](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/deploy),
[networking](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/networking)).

The managed environment runs Python 3.11 or Node.js on Ubuntu 22.04. Dependencies come only from
`requirements.txt` (pip) or `pyproject.toml` (uv), so no system package can be installed: there is no
Java, and R is not a supported framework. The target therefore:
- fails for an `iom` profile with the §6.8 Java error;
- fails for an `ssh` profile with `target databricks_apps supports only http (Viya) profiles`;
- fails for an R app with `target databricks_apps does not support language r`.

The target writes `bundle/app.yaml`, `bundle/requirements.txt`, `databricks/app.json` and
`deploy-databricks.md`. When the folder has only contracts, the §6.8 generated `app.py` is added.

**Options.**

| Option | Default | Meaning |
|---|---|---|
| `app_name` | `sashiny-app` | App name: 2–30 characters, lowercase letters, digits and `-`, starting with a letter and not ending with `-` |
| `secret_scope` | `sashiny` | Secret scope that holds the keys `sas-user` and `sas-password` (1–128 characters: letters, digits, `_`, `-`, `.`) |
| `private_connectivity` | false | `true` confirms that a network connectivity configuration routes the workspace's serverless egress to SAS privately; the private-network option of this target |

`app.yaml`:
```yaml
# Generated by SAShiny <VERSION> (CONTRACT.md 6.8.6). Do not edit by hand.
command: ["shiny", "run", "app.py", "--host", "0.0.0.0", "--port", "$DATABRICKS_APP_PORT"]
env:
  - name: "<NAME>"
    value: "<value>"
  - name: "SASHINY_SAS_USER"
    valueFrom: "sas-user"
  - name: "SASHINY_SAS_PASSWORD"
    valueFrom: "sas-password"
```
The file has one `value` entry per plain variable of §6.8, in order, and the two `valueFrom` entries.
`valueFrom` names the app's secret resources `sas-user` and `sas-password`.

`requirements.txt` holds one line after its comment: `sashiny[shiny,saspy,upload,plotnine]==<VERSION>`.

`databricks/app.json` is the request body of `databricks apps create`:
- `name`;
- `description`: `SAShiny app`;
- `resources`: the two secret resources (`scope`, `key`, permission `READ`).

The JSON is written with two-space indentation and a final newline.

`apply` runs, in order. Each `databricks` command gets `--profile <databricks_profile>` when that
option is given:
1. `databricks apps create --json @<out_dir>/databricks/app.json`, only with the option
   `create: true`;
2. `databricks sync <out_dir>/bundle <source_code_path>`;
3. `databricks apps deploy <app_name> --source-code-path <source_code_path>`.

The apply options are `source_code_path` (required: a workspace path starting with `/Workspace/`),
`create` (default false) and `databricks_profile` (a CLI profile name; `profile` is the SAS profile). `doctor` reports, in order: `databricks` missing from `PATH`,
and `databricks current-user me` failing (no configured profile). The exact bytes are fixed by
`spec/fixtures/deploy/databricks_*`.

### 6.9 Streamlit front end (Python only)

`streamlit_app(contracts, engine, *, title=None)` in the module `sashiny.streamlit_app` renders one
or more contracts as a Streamlit app. `engine` is an engine, a pool, or a function that returns one
(for example `sashiny.connect_from_env`), called once per server process. With several contracts, a selectbox in the sidebar chooses the program. It is the
Streamlit counterpart of `sashiny.app` and has no R equivalent: Streamlit is a Python framework
(tracked in an issue).

The front end changes only the widgets. It uses, unchanged:
- contract loading and validation (§3);
- value validation (§4, V001–V014) and rendering (§5);
- the wrapper and its injection rules (§6.3);
- `choices_from` (§6.4) and the engines, pool and timeouts (§6.5, §6.6);
- collection (§8).

Inputs are read into the JSON form of §2.1 and passed to `engine.run`. An invalid value is reported
from the run's `metadata.issues`, as in the Shiny module.

**Inputs.** Each input maps to one widget, in `ui.order`, then contract order. The widget label is
the input `label`, and its `help` is the input `help`. Widget keys are `sashiny-<module>-<input>`.

| Input type | Widget | Value passed to the run |
|---|---|---|
| `numeric` | `st.number_input` (`min_value`, `max_value`, `step`; integer step and format when `integer`) | number, or `null` when empty |
| `text` | `st.text_input` (`max_chars` = `max_length`, `placeholder`) | string |
| `choice`, `widget: select` | `st.selectbox` (`index` of the default, or none) | value, or `null` |
| `choice`, `widget: radio` | `st.radio` | value, or `null` |
| `multichoice`, `widget: select` | `st.multiselect` (`max_selections` = `max_selected`) | list of values |
| `multichoice`, `widget: checkbox` | one `st.checkbox` per choice | list of the checked values, in choice order |
| `date` | `st.date_input` (`min_value`, `max_value`; `today` resolved) | ISO date, or `null` |
| `daterange` | `st.date_input` with a `(start, end)` value | `[start, end]` ISO dates, or `null` until both are chosen |
| `dataset` | `st.file_uploader` (`type` = `accept`), plus `st.checkbox` "Use the sample file" when `sample` is set | the upload, or the sample |

Choice labels are shown with `format_func`; the values are passed. `choices_from` inputs are filled
from `engine.choices` once per browser session. A failure is shown with `st.error` and leaves the
choices empty. An upload over `max_size_mb` is refused before the run (V014), as in §7.

**Runs.** The Run button has the label `ui.run_label`. It starts the run in a background thread and
keeps the thread in `st.session_state`, so reruns of the script never block on SAS. While the run
is in progress, the app shows `st.status("Running...")` and polls every second. A second click
while a run is in progress is ignored. The run's own `timeout_seconds` (§6.5) applies unchanged.
`ui.auto_run` starts one run when the session opens.

**Outputs.** Outputs are rendered in contract order once a run has finished, each under an
`st.subheader` with the output `label`:

| Output type | Element |
|---|---|
| `table` | `st.dataframe` of the rows (column labels as headers); `st.caption` "Showing n of m rows." when truncated |
| `plot` | `st.image` per graph; `st.caption` "No graphs were produced." when empty |
| `chart` | the §8.5 chart rendered with `st.plotly_chart` (plotly) or `st.pyplot` / `st.image` (plotnine, matplotlib) |
| paired (§8.6) | `st.tabs(["SAShiny", "SAS"])`, with the default view first |
| `html` | `st.iframe` of a fixed wrapper that holds the document in an inner `<iframe sandbox="">` (`srcdoc`, HTML-escaped), so the document runs no scripts; `st.components.v1.html` on Streamlit versions without `st.iframe` |
| `log` | `st.code` of the lines |
| `download` | `st.download_button` with the file name and MIME type |

An output value `{"error": ...}` is shown with `st.error`. The run status (§6.5) and run id are
shown with `st.caption`. Errors and warnings use `st.error` and `st.warning`. The full log is in an
`st.expander` "SAS log".

The widget mapping is fixed by `spec/fixtures/streamlit/widgets.json`: one case per input type and
widget variant in `spec/sashiny.schema.json`.

### 6.10 External values for the Shiny module

`sas_program_server()` (R) and `program_server()` (Python) accept an optional `values` argument: a
reactive that returns a named list (R) or dict (Python) of input values in the §2.1 JSON form. It
lets other Shiny code, such as a filter panel in a parent module, drive a contract's inputs.

**Precedence.** For every id that `values()` supplies, the supplied value replaces the UI value; ids it
does not supply are read from the UI as usual. A supplied `null` / `NULL` replaces the UI value with an
absent value (so a required input gives `V001`). The merged values are validated
(§4, V001–V014) exactly like UI values, so an invalid or unknown external value gives the same codes
(for example `V003`, `V004`, `V011`) and no SAS code is submitted.

**Dataset inputs.** A value supplied for a dataset id is a data frame: an R `data.frame` (a tibble
counts) or a pandas `DataFrame`. It replaces the upload control and the `sample` checkbox: it is
written as a CSV file named `<id>.csv` in the canonical form of §7.1, and that file goes through the
same conversion and checks as an uploaded file (§7; `accept` must include `csv`, `max_size_mb` applies
to the CSV bytes, declared `columns` must be present), so a problem gives `V014` and no SAS code is
submitted. A supplied `null` / `NULL` makes the dataset input absent. Any other value for a dataset
id is `V014`. Because the CSV bytes are canonical, the same data frame gives the same upload SHA-256
in R and Python, so result-cache and recording keys (§6.11, §8.3) agree across languages.

**Triggers.** A run starts on a Run click, as before. In addition, when `ui.auto_run` is `true`, every
change of `values()` starts a run once `values()` has been stable for the debounce interval
(`debounce_ms`, default `500`). The first value of `values()` does not start an extra run (the
`auto_run` run at session start already uses it). A change while a run is in progress starts one
run after it finishes, with the latest values; intermediate changes are dropped. When `ui.auto_run`
is `false`, `values()` changes never start a run.

**Hiding controls.** With `hide_inputs = TRUE` (Python `hide_inputs=True`), the UI controls of the
ids currently supplied by `values()` are hidden; the other controls and the Run button stay visible.
The default (`FALSE`) shows every control, even when its value is overridden.

### 6.11 Result cache (opt-in)

With `run.cache: true`, a run whose inputs are identical to an earlier successful run reuses that
run's result instead of submitting the program again. The default is `false`: without it every run
reaches SAS.

**Key.** The cache key is the lower-case hex SHA-256 of this UTF-8 text, built line by line with LF
endings:

```
sashiny-cache-key 1
contract <contract_sha256>
program <program_sha256>
macro <NAME>=<VALUE>          one line per rendered macro, in 5.7 order
upload <input_id> <sha256>    one line per supplied dataset input, contract order; sha256 of the file bytes
```

`contract_sha256` and `program_sha256` are those of §8.4. The rendered values include resolved
`"today"` defaults and bounds, so a run on another day has another key. The key is computed after
value validation; a run whose values do not validate (V001–V014) is never looked up or stored and
fails exactly as without the cache. `spec/fixtures/collect/cache_key.json` fixes the key text.

**Storage.** Only results with status `success` or `warning` are stored; `error`, `timeout` and
engine failures never are. A stored result is reused for `run.cache_ttl_seconds` (default `3600`)
after it was stored. The cache is per process and shared by every engine and pool of that process;
it holds at most 100 results by default and evicts the least recently used one when full.
Implementations provide a hook to replace the in-memory store (for example with an external cache);
they do not ship an external store.

**Hits.** A reused result keeps its original `run_id`, `log`, outputs and metadata, and adds
`metadata.cache_hit = true` and `metadata.cached_at` (the UTC time when it was stored, in the §8.4 form). A run
that does not hit the cache has no `cache_hit` field. Each hit returns a copy, so changing a returned
result does not change the cache.

**Non-deterministic programs.** The key covers only the contract, the program file and the inputs. A
program whose result also depends on the current date or time (beyond `"today"` inputs), random
numbers, or data outside its inputs (database tables, files, `SASHELP` views that change) MUST leave
`run.cache` off; otherwise users see stale results. The program file is hashed, but files it
`%include`s are not.

### 6.12 Scripted runs and defaults

`sas_run(contract, engine, values)` (R) and `run(contract, engine, values)` (Python) start a run
without the Shiny module, with the same precedence as §6.10 and the contract's defaults in place of
the UI. For every id that `values` supplies, the supplied value is used; every other non-dataset
input that has a `default` takes that default, with `"today"` (in a `date` default or either item of
a `daterange` default) resolved to the run's `today` date in `YYYY-MM-DD` form, exactly as the module
shows it when the app starts. A supplied `null` / `NULL` (R `list(id = NULL)`, Python `{"id": None}`)
makes the input absent, so a required input gives `V001`. Inputs without a `default`, and dataset
inputs (which are supplied through `uploads`), are absent unless supplied. Omitting `values`, or
passing `NULL` / `None` or an empty list / dict, therefore runs every input at its default, which is
what a first click of Run in the generated app submits. The merged values are then validated (§4) and
keyed (§6.11) like any other values.

---

## 7. Dataset upload conversion

A data frame supplied through `values` (§6.10) or `sas_run(uploads = )` / `run(uploads=)` is
first written as CSV in the canonical form of §7.1 and then converted like any other file.

1. Read the file by extension: `csv` (UTF-8, comma, header row, RFC 4180), `xlsx` (first sheet, header
   row), `xpt` (SAS transport v5/v8), `sas7bdat`.
2. Column names: replace characters outside `[A-Za-z0-9_]` with `_`; prefix `_` if the first character is
   a digit; truncate to 32 bytes; resolve case-insensitive duplicates by suffixing `_2`, `_3`, ... (truncating
   further to fit). Declared `columns` are matched case-insensitively **after** this step.
3. Declared column types: `numeric` (parse as number, empty = missing; unparseable = `V014`), `character`,
   `date` (ISO `YYYY-MM-DD`, or a native date type; stored as SAS date with format `DATE9.`). For `numeric`
   and `date` columns, a value is "empty" (missing) when it is the empty string or whitespace only; any
   other non-conforming value (including the literal text `NA`, `nan`, `NaT` or `None`) is unparseable and
   reported as `V014`.
4. Undeclared columns: native numeric/date types are kept. In `csv`, a column whose non-empty values all
   parse as numbers becomes numeric, otherwise character.
5. The result is written to `target`. Column order is preserved.
6. A supplied dataset input is either a user file or, if the UI offers it, the contract's `sample` file.
   Both go through steps 1–5.

The `max_size_mb` limit is enforced when the file is received, not only when it is converted: an
upload larger than the declared limit MUST be rejected (or its storage aborted) before the whole file
is written, so a client cannot fill server storage with a file the contract would refuse.

The transport layer enforces the *largest* declared `max_size_mb` across all dataset inputs (R raises
`shiny.maxRequestSize` to that value; Shiny for Python has no transport-level cap hook, so the check
runs at the earliest SAShiny-controlled point, in `shiny_values`). A file over one input's limit but
under the largest is still stored by the transport and then rejected by the per-input `read_upload`
check (V014). This is the best the Shiny upload protocol allows; the per-input limit is always
enforced before any SAS work.

Blank lines in `csv` (step 1): when the header line has exactly one field, every line after it is a
row, so an empty line is a row whose value is missing, as RFC 4180 reads it. This is how §7.1 writes
a missing value or `""` in a one-column data frame. The line terminator that ends the last row does
not start another row (`A\nx\n\ny\n` has three rows). With more than one column, blank lines are
skipped (the canonical writer never produces one: its empty rows are `,` or longer).

### 7.1 Canonical CSV for data frames

R and Python write the same bytes for the same data frame:

1. UTF-8 without a byte order mark. Every line, including the last, ends with LF.
2. The first line holds the column names, as given (§7 step 2 cleans them later). One line per row
   follows, in row order. Row names (R) and the index (pandas) are not written.
3. Fields are separated by `,`. A field is enclosed in `"` only when it contains `,`, `"`, CR or LF;
   a `"` inside is doubled.
4. A missing value (R `NA`, Python `None`, `NaN`, `NaT`, `pd.NA`) is an empty field. So is an empty
   string. In a one-column data frame such a row is an empty line, which §7 reads back as a row.
5. Values by column type:

| Column | Field |
|---|---|
| character, string | the text |
| factor (R), category (pandas) | the label, written by the rule for its values' type |
| logical (R), bool (pandas) | `1` for true, `0` for false |
| integer | the decimal digits, with `-` if negative |
| double, float | C `printf` `%.17g`, correctly rounded (so `0.1` is `0.10000000000000001` and `64` is `64`), which always reads back to the same number; infinite values are `V014` |
| date: R `Date`; Python `datetime.date` values | `YYYY-MM-DD` |
| date-time: R `POSIXct`; pandas `datetime64`, Python `datetime.datetime` values | `YYYY-MM-DDTHH:MM:SS` in UTC, then `.` and up to six fractional digits without trailing zeros when the time, rounded to the microsecond, has a fraction, then `Z`. A date-time without a time zone (naive) counts as UTC |

   A pandas `object` column is written value by value with the rule for each value's type. Any
   other type (R list columns, complex numbers, durations, nested objects) is `V014`, naming the
   column. A data frame with no columns is `V014`; one with no rows is just the header line.

`spec/fixtures/frames/cases.json` pins this down byte for byte.

---

## 8. Result collection

Collection is step 4 of the run protocol (6.1). It happens after the main submission and in contract output
order. A failure collecting one output MUST NOT change the run status or stop collection of the other
outputs. The failed output's value is `{"error": "<message>"}`, and the message is also appended to
`metadata.collect_errors`.

### 8.1 Output values

Each output has a **language-neutral JSON value**. Engines return it, and the internal test mock replays it
from recordings (8.3), so R and Python see identical data.

| Output | Value |
|---|---|
| `table` | `{"columns": [{"name", "type", "label", "format"}], "rows": [[...], ...], "total_rows": int or null, "truncated": bool, "formatted": bool}` |
| `plot` | `[{"mime": "image/png" \| "image/svg+xml" \| "image/jpeg" \| "image/gif", "data": "<base64>"}, ...]` |
| `chart` | The same shape as `table`: `{"columns": [...], "rows": [[...], ...], "total_rows": int or null, "truncated": bool, "formatted": bool}` |
| `html` | The ODS HTML document of the main submission, as a string |
| `log` | `[{"level": "error" \| "warning" \| "note" \| "text", "text": "<line>"}, ...]` |
| `download` | `{"filename": "<name>.<ext>", "mime": "<type>", "data": "<base64>"}` |
| paired `plot` or `chart` (2.2) | `{"sas": <plot value>, "sashiny": <chart value>}` |

Table details:
- `type` is `"numeric"` or `"character"`. `label` and `format` are `""` when SAS has none.
- With `formatted: false`, numeric cells are JSON numbers, or `null` for SAS missing values. Character
  cells are strings with trailing blanks removed. SAS dates stay numbers.
- With `formatted: true`, every cell is the string SAS displays (`vvalue`), with leading and trailing
  blanks removed.
- "Blanks" here means ASCII whitespace (space, tab, CR, LF, vertical tab, form feed), not the full
  Unicode `White_Space` set. R and Python MUST strip the same characters so the JSON value is identical.
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

**chart**: Read the dataset exactly like a `table` (the same column-metadata and row-read steps above),
and return the same value shape. The chart is rendered client-side by the Shiny module from this data;
SAS produces no image. `spec` (declarative) or `render` (a per-language callback) describes the chart
(see 8.5).

**paired** (2.2): Collect `sas` like a `plot` with `select` = `sas_plot` (chart form) or the plot's
own `select` (plot form). Collect `sashiny` like a `chart` from the chart fields (chart form) or the
`chart` mapping (plot form). The two parts are independent: if one part fails, its value is
`{"error": "<message>"}`, the message is appended to `metadata.collect_errors` as
`<output_id>.<part>: <message>`, and the other part is still collected.

**html**: The ODS HTML listing returned by the main submission.

**log**: Split the main-submission log on line breaks (`CRLF`, `CR` or `LF`). If the log ends with a line
break, there is no empty final line. Drop trailing whitespace from each line: ASCII blanks only, as in
8.1 (a no-break space, U+3000 or U+0085 stays).
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

A recording replays a run without SAS. Recordings are **internal test fixtures only** (6.6). They let the
automated checks (CRAN, PyPI, CI) exercise the module and collection code without SAS. They are
not reachable through the public API. Users cannot create them from a live engine or feed them into an app.
A recording is a UTF-8 JSON file `<key>.json`:

```json
{"sashiny_recording": 1, "status": "...", "log": "<full main-submission log>",
 "outputs": {"<output_id>": <value from 8.1>}, "sas_version": "...",
 "contract_sha256": "...", "program_sha256": "...", "macros": {"NAME": "VALUE"},
 "recorded_at": "<UTC, §8.4 form>"}
```

`<key>` is the lower-case hex SHA-256 of this UTF-8 text, built line by line with LF endings:

```
sashiny-recording-key 1
contract <contract_sha256>
macro <NAME>=<VALUE>          one line per rendered macro, in 5.7 order
upload <input_id> <sha256>    one line per supplied dataset input, contract order; sha256 of the file bytes
```

The key depends only on the contract bytes, the rendered values and the uploaded files. A recording
written by either language's test suite therefore replays in both. The internal mock engine with no matching recording returns
status `success` with empty outputs and sets `metadata.recording` to `"missing"`.

### 8.4 Run metadata

Every result carries run metadata: `run_id`, `contract_sha256` (of the YAML bytes), `program_sha256`
(of the program file bytes as stored on disk), rendered macro values, start/end timestamps (`started_at`, `ended_at`),
engine name and version, SAS version (`&SYSVLONG`), status, and `collect_errors` (list, possibly empty).

Both languages write the same bytes for these fields:
- Timestamps (`started_at`, `ended_at`, `recorded_at` in 8.3 and `cached_at` in 6.11) have the form
  `YYYY-MM-DDTHH:MM:SSZ`: UTC, whole seconds, a literal `Z`. Readers MUST also accept other ISO 8601
  UTC forms (for example `+00:00` with fractional seconds, as written by Python up to 0.3.1).
- `engine_version` is the SAShiny package version (equal in R and Python, section 11) for every
  engine, including the internal test mock.

### 8.5 Chart spec (client-side rendering)

A `chart` output is rendered by the Shiny module, not by SAS. Exactly one of `spec` (declarative, in
the contract) or `render` (a per-language callback, supplied in code) is given.

**`spec` (declarative)** — a mapping with these fields:

| Field | Required | Meaning |
|---|---|---|
| `kind` | yes | `scatter`, `line`, `bar`, `histogram` or `box` |
| `x` | yes | column mapped to the x axis (or the single variable for `histogram`) |
| `y` | no | column mapped to the y axis (required for `scatter`, `line`, `bar`, `box`) |
| `color` | no | column mapped to colour |
| `fill` | no | column mapped to fill |
| `facet` | no | column mapped to a facet |
| `title` | no | chart title |
| `subtitle` | no | chart subtitle |
| `xlab` | no | x-axis label (defaults to the column name) |
| `ylab` | no | y-axis label (defaults to the column name) |
| `backend` | no | client-side graphics engine: `ggplot2`, `base` or `plotly` (R); `plotnine`, `matplotlib` or `plotly` (Python). Defaults to the language's primary backend (`ggplot2` / `plotnine`). |

Column names are matched case-insensitively against the collected columns. An unknown column is a
collection error. The exact visual output is backend-specific; the data and the mapping are the
portable contract. A backend MUST honour every declared mapping (`x`, `y`, `color`, `fill`, `facet`)
that its kind supports; if a backend cannot honour a mapping it MUST report a collection error rather
than silently render a chart that ignores it. The secondary backends (`base`, `matplotlib`) group
`scatter` and `line` charts by `color` and `bar` charts by `fill`, and draw no other `color` or
`fill` mapping, except a `box` chart whose `color` is its own `x` column. Any other `color`/`fill`
mapping is the error `chart backend <backend> cannot map <field> for kind <kind>`. `plotly` draws
`color` or `fill`, not both: both together are the error
`chart backend plotly cannot map both color and fill`. `xlab`, `ylab`, `title` and `subtitle` are
honoured by every backend (`subtitle` only together with `title` in `plotly`).

**`render` (callback)** — a per-language extension, not part of the cross-language fixtures and not a
YAML field. In R it is a function `function(value, spec, ...)` returning a plot object; in Python it
is a callable `(value, spec) -> object`. The Shiny module calls it with the collected chart value and
the output's `spec` mapping (or `None`/`NULL` when absent). The callback is supplied to the module
server (e.g. `sas_program_server(..., render = list(<output_id> = fn))` in R, or a `render` mapping in
Python), following the same "render callback" pattern as `shiny::renderPlot` and
`shiny.render.plot`.

### 8.6 Paired outputs and the view toggle

A paired output (2.2) is rendered by the Shiny module as one card with two views: `sas` (the
original SAS graph, rendered like a `plot`) and `sashiny` (the client-side chart, rendered like a
`chart`, 8.5). The behaviour is identical in R and Python:

- Both views are rendered into the card once per run. Switching views happens in the browser only;
  it MUST NOT re-run SAS or re-render the card on the server.
- **Per-card toggle:** each paired card shows two buttons, `SAS graph` and `SAShiny chart`, with
  `aria-pressed` marking the visible view.
- **Module toggle:** a program module with at least one paired output shows one more pair of
  buttons, `SAS graphs` and `SAShiny charts`, above the outputs. It switches every paired card of
  that module. A later per-card choice overrides it for that card only.
- The view chosen for a card, or by the module toggle, persists when the card re-renders after a
  new run, for the life of the browser tab.
- A view whose part failed (8.2 paired) shows the part's collection error, like an unpaired output.
- **Default view:** `sashiny`. The module server takes a `chart_view` argument: `"sashiny"`,
  `"sas"`, or a mapping from paired output ids to either value (unlisted paired outputs use
  `sashiny`). An unknown value or an id that is not a paired output is an error when the server
  starts.
- **Toggle on/off:** the toggles are shown by default. The module takes a `chart_toggle` argument
  (default true). With `chart_toggle` false neither the per-card nor the module toggle is shown,
  and each paired card shows only its default view.
- `chart_view` and `chart_toggle` are code arguments, not YAML fields; the app helpers pass them
  through to every module.

### 8.7 Language accessors (non-normative)

The §8.1 values are the cross-language wire format and do not change. Each package also offers data
frame accessors. Both languages produce the same column names, types, row counts and log types.

| Accessor (R / Python) | Returns |
|---|---|
| `sas_result_table(result, id)` / `Result.table(id)` | One row per table row, one column per §8.1 column, by `name`. Numeric columns (`formatted: false`) are doubles with SAS missing as `NA` / `NaN`; other columns are character, with missing as `NA` / `None` |
| `sas_result_log(result)` / `Result.log_frame()` | One row per line of the run's full log (§8.2 line splitting), with columns `line` (integer, from 1), `type` and `text` |
| `sas_result_outputs(result)` / `Result.frames()` | A named list / dict: each `table` and `chart` output as a table frame, each `log` output as a log frame (its `type` from the §8.1 `level`), and every other output's §8.1 value unchanged |

- Per-column `label` and `format` are kept as column attributes: R uses `label` and `format.sas`
  (as 'haven' does), Python uses `DataFrame.attrs["labels"]` and `attrs["formats"]`, keyed by
  column name. `truncated` and `total_rows` are frame attributes in both languages (`attrs` in
  Python).
- `type` is `"ERROR"`, `"WARNING"` or `"NOTE"` for lines starting with that word (§6.5), otherwise
  `"other"`. The status rules and this column use the same classifier, so they cannot disagree.
- A missing output id, or an id whose output is not a table or chart, is an error that names the id.
  So is an output that holds `{"error": ...}`. Python needs pandas, an optional extra; without it the
  accessors raise `ImportError`, naming the extra to install.

The accessors are fixed by `spec/fixtures/collect/frames.json`.

---

## 9. Known constraints (documented, not errors)

- If the program sets one of the injected macro variables itself (e.g. `%let min_msrp = 5;`), the
  program's value wins. Lint reports this (`L001`) by scanning for `%let <NAME>` and
  `call symput[x]('<NAME>'`, except assignments inside a
  `%if not %symexist(<NAME>) %then %do; ... %end;` guard. Programs written for standalone use SHOULD guard defaults with
  `%if not %symexist(NAME) %then %do; %let NAME = ...; %end;` (SAS 9.4M5+ open-code `%if`).
- A program that ends the session (`endsas;`) or leaves unbalanced quotes produces status `error`
  (missing END sentinel). So does a program that leaves `options nonotes;` in effect, because SAS then
  drops the `NOTE:` sentinels.
- Macro-quoted values are **not** automatically unquoted when passed to the compiler. In particular,
  `WHERE` clauses do not unquote them, so a macro-quoted value such as `'Asia' 'Europe' 'USA'` causes a
  syntax error in `where origin in (&NAME)`. A macro-quoted value is also kept as a separate token, so
  a name built from it (`l&NAME`) splits in two. For this reason SAS-literal values are emitted without
  `%superq`, `entry: macro` call arguments mask only single characters (see §6.3), and only `raw`
  text/choice values are macro-quoted. A program may use
  `%unquote(&NAME)` where a quoted token must be resolved, but it MUST NOT be required for ordinary
  `WHERE` clauses.

## 10. Lint (advisory)

| Code | Finding |
|---|---|
| `L001` | Program assigns an injected macro variable outside a `%symexist` guard (section 9). The guard exemption applies only to assignments inside the guard; a later assignment to the same macro outside any guard is still `L001`. Under `run.entry: macro`, an assignment to `NAME` is also exempt when it lies inside the definition of the entry macro itself (from `%macro <MACRO>(` to the next `%mend`) and `NAME` is one of that macro's parameters (a name in the parenthesised parameter list, matched case-insensitively): this is parameter self-normalisation and the value is local to the macro. The same assignment outside that definition, or to a name that is not a parameter, is still `L001`. |
| `L002` | Injected macro variable never referenced in the program (`&NAME` not found, case-insensitive). |
| `L003` | `table`/`chart`/`download` `from` dataset, or the `chart.from` of a paired `plot`, never created in the program and not a dataset input target or a permanent library. |
| `L004` | More than one `rtf`/`pdf` download: each receives the same output; usually unintended. |
| `L005` | `entry: macro` but `%macro <MACRO>` not found in the program. |

## 11. Versioning

`sashiny: 1` will only ever receive backward-compatible additions: new optional fields with defaults
that preserve existing behaviour. Any breaking change becomes `sashiny: 2`. Wrapper changes that alter
generated bytes require a new wrapper version line (`/* SAShiny 1 wrapper ... */`).

**Release numbers.** The spec has a release number `<major>.<minor>` (shown under the title). The
major part is the contract version (`sashiny: 1`). The minor part goes up with every change to this
document, the schema or the fixtures that implementations must follow. Both packages record the spec
release they implement and print it with `sas_info()` (R) and `sashiny.info()` (Python). The R
package and the Python library are released together with the same version number (lockstep), and
CI fails when the two package versions, or the spec release recorded in either package, differ from
this document.

## 12. Fixtures

See [`fixtures/README.md`](fixtures/README.md).
