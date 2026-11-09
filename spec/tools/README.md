# Spec tools

| Script | Purpose | Runs in |
|---|---|---|
| `sashiny_ref.py` | Small reference oracle for CONTRACT.md. Keeps fixtures consistent. Never shipped. | CI |
| `check_spec.py` | Validates the schema, every fixture and every example contract | CI (`spec` workflow) |
| `live_sas_check.py` | Runs the contract against **real SAS** through saspy and writes a JSON report | Your machine |

## Live SAS check

Prerequisites: [uv](https://docs.astral.sh/uv/). For IOM connections (SAS OnDemand, SAS 9.4 IOM) you
also need Java 8 or newer: `java -version`. On macOS, `brew install --cask temurin` works.

1. Put credentials in `~/.authinfo` (Windows: `%USERPROFILE%\_authinfo`). Never put them in the repo.
   Restrict the file on macOS/Linux with `chmod 600 ~/.authinfo`.
   ```
   oda user <ODA user ID or e-mail> password <ODA password>
   viya user <Viya user> password <Viya password>
   iom user <SAS 9.4 user> password <SAS 9.4 password>
   ```
2. From the repository root, run one profile:
   ```sh
   # SAS OnDemand for Academics (pick your home region: us1, us2, eu1, ap1, ap2)
   uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
     python spec/tools/live_sas_check.py --profile oda --oda-region us1

   # SAS Viya
   uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
     python spec/tools/live_sas_check.py --profile viya --url https://<viya-host> \
     --context "SAS Studio compute context"

   # SAS 9.4 workspace server (IOM)
   uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
     python spec/tools/live_sas_check.py --profile iom --host <sas-host> --port 8591

   # SAS 9.4 over SSH (key-based login)
   uv run --no-project --with saspy --with "pandas<3" --with pyyaml --with jsonschema \
     python spec/tools/live_sas_check.py --profile ssh --host <sas-host> \
     --saspath /opt/sas/SASHome/SASFoundation/9.4/bin/sas_u8
   ```
3. Share the generated `sashiny-sas-check-<profile>.json`. It contains SAS version, timings, pass/fail
   results and log excerpts on failure. It never contains credentials.

The check covers the session, submissions, ODS graphics, data round-trips (dates, Unicode, missing values),
every byte-exact wrapper fixture, hostile text inputs (`'; endsas; %sysexec ...`), ODS RTF/PDF destinations
with `id=`, and the three example programs with their default inputs.
