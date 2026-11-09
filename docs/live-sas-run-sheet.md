# Live SAS check — run-sheet

This is the step-by-step checklist for running `spec/tools/live_sas_check.py`
against each SAS profile and attaching the JSON reports to issue #11. The tool
validates the wrapper, the macro quoting and the three example programs on real
SAS before the engine work is finalised.

> **Owner:** Mehar. **Where:** ProCogia VPN (for Viya and 9.4). **Credentials:**
> `~/.authinfo` (macOS/Linux) or `%USERPROFILE%\_authinfo` (Windows). Never put
> credentials in the repo, the report, or a commit.

## Prerequisites (once)

1. **uv** — `uv --version` (any recent version).
2. **Java 8+** for IOM connections (ODA and 9.4 IOM). Check `java -version`.
   On macOS: `brew install --cask temurin`.
3. **`~/.authinfo`** with one line per profile (see below). Restrict it:
   `chmod 600 ~/.authinfo`.
4. **ProCogia VPN** connected for the Viya and 9.4 profiles.

## `~/.authinfo` entries

```
oda user <ODA user ID or e-mail> password <ODA password>
viya user <Viya user> password <Viya password>
iom user <SAS 9.4 user> password <SAS 9.4 password>
```

The SSH profile uses key-based login (no password line needed).

## Run each profile

Run from the repository root. Each command writes
`sashiny-sas-check-<profile>.json`.

### 1. SAS OnDemand for Academics (ODA, SAS 9.4)

Pick your home region (`us1`, `us2`, `eu1`, `ap1`, `ap2`):

```sh
uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
  python spec/tools/live_sas_check.py --profile oda --oda-region us1
```

### 2. SAS Viya (HTTP)

```sh
uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
  python spec/tools/live_sas_check.py --profile viya --url https://<viya-host> \
  --context "SAS Studio compute context"
```

### 3. SAS 9.4 workspace server (IOM)

```sh
uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
  python spec/tools/live_sas_check.py --profile iom --host <sas-host> --port 8591
```

### 4. SAS 9.4 over SSH (key-based)

```sh
uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
  python spec/tools/live_sas_check.py --profile ssh --host <sas-host> \
  --saspath /opt/sas/SASHome/SASFoundation/9.4/bin/sas_u8
```

## What "pass" looks like

The tool runs 9 checks and prints a summary line per check:

```
  PASS    env        0.1s
  PASS    connect    2.3s
  PASS    submit     0.4s
  PASS    graphics   1.1s
  PASS    roundtrip  0.8s
  PASS    wrapper    3.2s
  PASS    injection  1.5s
  PASS    ods_ids    0.6s
  PASS    examples   4.0s
```

A profile is green when **all 9 checks pass** (the final line reads
`9 passed, 0 failed, 0 skipped`). A non-zero exit code means at least one check
failed — read the `error` and `traceback` fields in the JSON report.

## Attach the reports

1. Confirm each `sashiny-sas-check-<profile>.json` contains **no credentials**
   (grep for `password`, `authkey` values, or your user id).
2. Attach the four JSON files to issue #11, one per profile.
3. Note any failed check and its `error`/`traceback` in the issue.

## Troubleshooting

- **`no SAS session`** on a check → the `connect` check failed; fix the profile
  (VPN, host, authinfo) and re-run.
- **Java not found** → set `JAVA_HOME` or pass `--java /path/to/java`.
- **Viya TLS error** → add `--no-verify-ssl` (only for self-signed test hosts).
- **ODA account not created** → create it first; otherwise skip ODA and note it
  in the issue (the demo falls back to Offline).