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
| `container` (Python) | Igor (@igor-procogia) | verified | 2026-11-17 | Local Docker 27.3.1, `linux/amd64` (emulated on Apple silicon) | ODA `us1` (IOM) | `sha256:459722c8d98f` | PyPI `sashiny` 0.3.0; Dockerfile from branch `fix/deploy-container-images` | Steps 1–7 pass: two runs (`69e84800`, `e28ea426`) with a reload between, SAS log timestamps match each run, no secret value in the container logs. Docker has no secret store, so `docker inspect` shows the SAS credentials to anyone with Docker access on the host; use the platform's secret store in production. |
| `container` (R) | Igor (@igor-procogia) | failed | 2026-11-17 | Local Docker 27.3.1, `linux/amd64` (emulated on Apple silicon) | ODA `us1` (IOM) | | branch `fix/deploy-container-images` | Step 1 fails as generated: the image installs `procogia/SAShiny/R@r-v<VERSION>` and no `r-v*` tag exists. With `R/` installed from source instead, the image passed a live ODA run. **Unblocked by `r-v0.3.1` (2026-11-20); re-verify.** |
| `azure_container_apps` | Igor (@igor-procogia) | generated only | | | | | | |
| `aws_ecs_express` (Python) | Igor (@igor-procogia) | failed | 2026-11-23 | AWS ECS on Fargate, `ca-central-1`, 1 task, ALB with a self-signed certificate imported into ACM; image built with Docker 27.3.1, `linux/amd64` (emulated on Apple silicon) | ODA `us1` (IOM) | `sha256:596e8ebc5369` | PyPI `sashiny` 0.4.1; generated from `main` at `c10400b` | Fails as generated: steps 2–3 never finish (the run stays at "running..."), because the service security group allows outbound TCP 443 and 8591 only, and ODA moves each SAS session to a port in the 88xx range (8801 and 8821 seen). With 4 changes to `infra/template.yaml`, steps 1–6 pass: two runs (`b0a75875`, `bb16f639`) on SAS 9.04.01M9P060525 with a reload between, SAS log timestamps match each run, CSV and PDF downloads work, `AWSALB` stickiness cookie set. The changes: (1) egress TCP 8800–8999 to `SasEgressCidr`; (2), (3) `RoleName: sashiny-app-*` and `PermissionsBoundary` on both IAM roles, which this account requires (deployed with `CAPABILITY_NAMED_IAM`); (4) `AssignPublicIp: ENABLED`, with the public subnets passed as `PrivateSubnetIds`, because this VPC has no NAT gateway. (2) to (4) are account-specific, but the template has no option for them. The SAS credentials are Secrets Manager secrets referenced by ARN; no secret value appears in the task definition or the CloudWatch logs. The container runs as uid 10001. ECS shows container health `UNKNOWN` (it ignores the Dockerfile `HEALTHCHECK`); the ALB health check is healthy. |
| `aws_ecs_express` (R) | Igor (@igor-procogia) | failed | 2026-11-23 | Same stack and account as the Python row, image switched to R | ODA `us1` (IOM) | `sha256:6d759496d415` | `install_github("procogia/SAShiny/R@r-v0.4.1")`; generated from `main` at `c10400b` | Same as Python: fails as generated (SAS session port blocked); with the same 4 template changes, steps 1–6 pass: two runs (`58e22bfe`, `2827a9ae`) on SAS 9.04.01M9P060525 with a reload between, the SAS log shows each run's id and time, CSV and PDF downloads work, no secret value in the task definition or logs. The R image builds from the `r-v0.4.1` tag as generated. |
| `snowflake_spcs` (Python) | Shreya (@shreya-sharma-procogia) | verified | 2026-11-18 | Snowflake SPCS, `AWS_US_WEST_2`, compute pool `CPU_X64_S` (1 instance); image built with Docker 29.1.2, `linux/amd64` (emulated on Apple silicon) | ODA `us2` (IOM) | `sha256:5fbee0a6679b` | PyPI `sashiny` 0.3.0; Dockerfile generated from `main` at `c452ba8` | Python app only. Steps 1–6 pass: two runs (`4ec33f27`, `ea781b54`) on SAS 9.04.01M8P022223 with a reload between, and the SAS log matches each run. The SAS credentials are a Snowflake `PASSWORD` secret passed with `secretKeyRef`; no secret value appears in `SYSTEM$GET_SERVICE_LOGS`. Deployed with a dedicated role that has only `CREATE DATABASE`, `CREATE WAREHOUSE`, `CREATE COMPUTE POOL`, `CREATE INTEGRATION` and `BIND SERVICE ENDPOINT`. saspy logs `Did not find key oda in authinfo file` before connecting; this is harmless, because the credentials come from the environment. |
| `snowflake_spcs` (R) | Shreya (@shreya-sharma-procogia) | generated only | | | | | | Not deployed: the generated R image installs `procogia/SAShiny/R@r-v<VERSION>`, and no `r-v*` release tag exists yet (#126). **Unblocked by `r-v0.3.1` (2026-11-20); re-verify.** |
| `posit_snowflake` | Shreya (@shreya-sharma-procogia) | generated only | | | | | | |
| `streamlit_snowflake` | Shreya (@shreya-sharma-procogia) | generated only | | | | | | |
| `databricks_apps` | Igor (@igor-procogia) | generated only | | | | | | |

When a deployment passes every step, change its status to **verified**. If any step fails, set it to
**failed** and open an issue.
