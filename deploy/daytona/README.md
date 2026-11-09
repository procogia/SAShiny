# Daytona sandbox — SAShiny demo (#12)

This directory holds the tooling to verify the Daytona sandbox for the hosted
SAShiny demo. The key question (from issue #12) is whether the ProCogia Daytona
tier allows **outbound TCP 8591** to `*.oda.sas.com` (SAS OnDemand for
Academics). That determines whether the hosted demo can offer the **ODA**
profile or is **Offline-only**.

## Prerequisites

1. A Daytona account (ProCogia's).
2. An API key from <https://app.daytona.io/dashboard/keys>.
3. The Daytona Python SDK: `pip install daytona`.

## Run the verification

```sh
export DAYTONA_API_KEY=...   # or put it in a gitignored .env file
python deploy/daytona/verify_sandbox.py
```

The script:

1. Creates a sandbox from a public base image (`ubuntu:22.04`).
2. Runs a hello-world check.
3. Tests outbound TCP 8591 to the ODA hosts **from inside the sandbox** (so it
   reflects the sandbox's egress policy, not your machine's).
4. Deletes the sandbox and prints a `TIER RESULT`.

## Interpreting the result

| Result | Meaning | Demo behaviour |
|---|---|---|
| `ODA reachable` | The tier allows outbound TCP 8591 | Hosted demo offers ODA + Offline |
| `ODA NOT reachable` | The tier blocks outbound non-HTTP egress | Hosted demo is Offline-only (default) |

`ODA NOT reachable` is expected on Daytona Tier 1/2 (restricted egress, no
override). Confirm the tier with ProCogia; if it cannot be raised, the hosted
demo defaults to Offline (recorded results), which is the documented fallback.

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