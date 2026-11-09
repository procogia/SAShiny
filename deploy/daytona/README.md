# Daytona sandbox — SAShiny demo (#12)

This directory holds the tooling to verify the Daytona sandbox for the hosted
SAShiny demo. The key question (from issue #12) is whether the ProCogia Daytona
tier allows **outbound TCP 8591** to `*.oda.sas.com` (SAS OnDemand for
Academics). That determines whether the hosted demo can offer the **ODA**
profile or is **Offline-only**.

## Result (verified 2026-11-09)

**ODA is reachable.** A sandbox created on the ProCogia Daytona account can make
outbound TCP 8591 connections to `odaws01-usw2.oda.sas.com` and
`odaws02-usw2.oda.sas.com` (`connect_ex` returned `0`). The hosted demo can
therefore offer the **ODA** profile in addition to Offline.

## Prerequisites

1. A Daytona account (ProCogia's).
2. The Daytona CLI, installed and authenticated (`daytona login`).

## Run the verification (CLI — no API key needed)

```sh
bash deploy/daytona/verify_tier_cli.sh
```

The script:

1. Creates a sandbox (default snapshot).
2. Tests outbound TCP 8591 to the ODA hosts **from inside the sandbox** (so it
   reflects the sandbox's egress policy, not your machine's).
3. Deletes the sandbox and prints a `TIER RESULT`.

## Run the verification (Python SDK — needs an API key)

```sh
export DAYTONA_API_KEY=...   # or put it in a gitignored .env file
python deploy/daytona/verify_sandbox.py
```

The SDK script additionally runs a hello-world check and uses a public base
image (`ubuntu:22.04`).

## Interpreting the result

| Result | Meaning | Demo behaviour |
|---|---|---|
| `ODA reachable` | The tier allows outbound TCP 8591 | Hosted demo offers ODA + Offline |
| `ODA NOT reachable` | The tier blocks outbound non-HTTP egress | Hosted demo is Offline-only (default) |

`ODA NOT reachable` is expected on Daytona Tier 1/2 (restricted egress, no
override). The verified result above shows the ProCogia tier **does** allow ODA
egress, so this fallback is not needed for the current account.

## The full demo image

The verification script uses a minimal public image for the egress test. The
full demo image (R + Python + Java 17 + saspy + both apps) is built from the
repository-root `Dockerfile`:

```sh
docker build -t sashiny-demo .
```

To host it on Daytona, push that image to a public registry with a tag (Daytona
requires a tag or digest, not `latest`), then create the sandbox from it:

```python
from daytona import Daytona, CreateSandboxFromImageParams
daytona = Daytona()
sandbox = daytona.create(CreateSandboxFromImageParams(image="<registry>/sashiny-demo:<tag>"))
```

## Credentials

The API key comes from `DAYTONA_API_KEY` (or a gitignored `.env`). SAS
credentials come from `~/.authinfo` or the Daytona secret store — **never** from
the image, the script, or the repo.