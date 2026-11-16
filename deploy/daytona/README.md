# Daytona sandbox — SAShiny demo (#12)

This directory holds the tooling to verify the Daytona sandbox for the hosted
SAShiny demo. The key question (from issue #12) is whether the ProCogia Daytona
tier allows **outbound TCP 8591** to `*.oda.sas.com` (SAS OnDemand for
Academics). That determines whether the hosted demo can offer the **ODA**
profile at all. SAShiny runs only on live, licensed SAS (spec §6.6), so there is
no offline fallback.

## Result (verified 2026-11-14)

**ODA is reachable.** A default Daytona sandbox on the ProCogia account
connected to five ODA hosts over TCP 8591; `https://welcome.oda.sas.com` also
returned HTTP 200. The hosted demo can therefore offer **ODA**. No login was attempted, so credentialed SAS execution remains to be
confirmed. See the issue's 2026-11-14 reachability results for host/IP details.

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
| `ODA reachable` | The tier allows outbound TCP 8591 | Hosted demo can connect to ODA |
| `ODA NOT reachable` | The tier blocks outbound non-HTTP egress | Hosted demo cannot run SAS; demo locally instead |

`ODA NOT reachable` means the hosted demo cannot run programs. Although Tier 1/2 may restrict egress,
the ProCogia account's current default sandbox was verified to allow ODA egress.

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

The container serves the Python app on port 8000 by default; the image also
includes the R package and R demo app. Set the sandbox's exposed port to 8000.
Set `SASHINY_PROFILE` (`oda` by default, or `viya` / `sas94`) and
`SASHINY_LICENSE_ACK=true` (after confirming the licence) on the sandbox.

### Preview URL and secrets

1. Configure SAS credentials as a runtime secret file mounted at
   `~/.authinfo`, or as the secrets `SASHINY_SAS_USER` / `SASHINY_SAS_PASSWORD`; do not use Docker build arguments, commit credentials, or bake
   them into the image. Users must obtain access to a compatible SAS compiler;
   SAShiny does not provide SAS.
2. Start the sandbox from the tagged image, expose port 8000, and verify the
   app and at least one scenario on live SAS.
3. Use Daytona's preview feature to generate a **signed URL with an expiry** for
   port 8000. Share that URL and its expiry with the audience; do not treat a
   permanent or unsigned preview address as the demo link.
4. If testing live ODA, inject the credentials through the runtime secret store
   and confirm a successful SAS login separately. TCP reachability alone does
   not verify credentials or a SAS session.

## Credentials

The API key comes from Daytona CLI authentication or `DAYTONA_API_KEY` (or a
gitignored `.env`) for the SDK. SAS credentials come from `~/.authinfo` or a
Daytona runtime secret file — **never** from the image, the script, or the repo.