# Deployment verification

Every deployment target (spec §6.8) is **generated only** until someone deploys the
`examples/general` demo to the real platform and records the result here. Do not advertise a
target as supported before then.

Generated files are checked automatically:
- the R and Python suites compare them with the hand-written fixtures byte for byte;
- the `deploy` workflow lints them with hadolint, `az bicep build`, cfn-lint and yamllint.

That proves the files are well formed. It does not prove that the platform accepts them.

## Checklist (per target)

1. Deploy `examples/general` with `sas_deploy()` or `sashiny.deploy.deploy()`, then follow the
   generated guide (or use `apply = TRUE`). Use a SAS ODA or SAS Viya account you are licensed for.
2. Open the app URL. The program's inputs are shown.
3. Click **Summarise**. The run finishes with status `success`, and the tables and graphs appear.
4. Open the **SAS log** output. The log is from this run: check the run id and the timestamps.
5. Reload the page and run again. The session reconnects and the run still works. With more than
   one replica, check that the browser stays on one replica (session affinity).
6. Check the platform's logs and environment. No secret value appears in them: SAS credentials and
   API keys show by name only.
7. Record one row below, then remove the deployment, unless it is meant to keep running.

## Record

Testing is split by platform. Igor covers the container, Azure, AWS and Databricks targets;
Shreya covers the three Snowflake targets, which share one Snowflake account setup.

| Target | Tester | Status | Date | Platform and region | SAS profile | Image digest or bundle id | SAShiny commit | Result and notes |
|---|---|---|---|---|---|---|---|---|
| `container` | Igor (@igor-procogia) | generated only | | | | | | |
| `azure_container_apps` | Igor (@igor-procogia) | generated only | | | | | | |
| `aws_ecs_express` | Igor (@igor-procogia) | generated only | | | | | | |
| `snowflake_spcs` | Shreya (@shreya-sharma-procogia) | generated only | | | | | | |
| `posit_snowflake` | Shreya (@shreya-sharma-procogia) | generated only | | | | | | |
| `streamlit_snowflake` | Shreya (@shreya-sharma-procogia) | generated only | | | | | | |
| `databricks_apps` | Igor (@igor-procogia) | generated only | | | | | | |

When a deployment passes every step, change its status to **verified**. If any step fails, set it to
**failed** and open an issue.
