# Daytona hosted demo (issue #12)

This runbook deploys the Python demo from the repository-root `Dockerfile` to a
Daytona sandbox. The same image contains the R package and R demo app, while
the default web process serves the Python app on port 8000. For the local R and
Python run commands, see [`../../docs/demo-run-sheet.md`](../../docs/demo-run-sheet.md).

## Before building

1. Record the synthetic demo scenarios and commit the recording JSON files.
   The repository currently has no recordings, so a fresh Offline profile
   cannot show results. Follow [`../../docs/recording-checklist.md`](../../docs/recording-checklist.md)
   and confirm all scenarios replay:

   ```sh
   cd Python && SASHINY_REQUIRE_RECORDINGS=1 uv run pytest tests/test_demo_scenarios.py
   ```

2. The ProCogia Daytona tier was verified on 2026-11-14: outbound TCP 8591 to
   ODA hosts is reachable. The hosted app therefore offers ODA and Offline;
   Viya and SAS 9.4 are hidden because they require the ProCogia VPN.

## Build and publish the image

Run these commands from the repository root. Replace the tag with a unique
release identifier; Daytona requires an image tag or digest, not `latest`.

```sh
IMAGE=ghcr.io/procogia/sashiny-demo
TAG=demo-2026-11-15
docker build -t "$IMAGE:$TAG" .
docker push "$IMAGE:$TAG"
```

Authenticate to the registry before pushing. Keep registry credentials out of
the Dockerfile and repository; choose a unique `TAG` for each published build.
The image defaults to `SASHINY_PROFILE=offline`
and `SASHINY_HOSTED=1`; it listens on port 8000. Do not pass SAS credentials as
Docker build arguments or bake them into the image.

## Create the Daytona sandbox and share a preview

1. In the ProCogia Daytona account, create a sandbox from the published image
   tag. Set the preview/service port to **8000**.
2. To enable live ODA, add the credentials as a Daytona runtime secret named
   `SASHINY_AUTHINFO` containing the `oda user <id> password <password>` line.
   The image entrypoint writes it to `~/.authinfo` with mode 0600, then removes
   the variable before starting the app. Never put this secret in the image or
   repository. If it is not configured, the app still starts in Offline mode.
3. Open the port 8000 preview and create a **signed preview URL with an
   explicit expiry** in Daytona. Share only that URL with the audience. The
   preview URL expires independently from the sandbox; do not make a permanent
   public link.
4. Open the link in a private browser window. Confirm the app loads, Offline
   replays the committed recordings, and ODA works only when runtime
   credentials are configured. Confirm Viya and SAS 9.4 do not appear in the
   hosted profile picker.
5. After the demo, stop or delete the sandbox and revoke/expire the preview
   URL.

Daytona account access, registry permissions, and creation of a signed preview
URL are external deployment actions; this repository does not contain a
published image or a live URL.

## Verify Daytona egress (when the tier changes)

The existing tier result is recorded above. To recheck from a sandbox with the
Daytona CLI installed and authenticated:

```sh
bash deploy/daytona/verify_tier_cli.sh
```

The script tests TCP 8591 from inside a temporary sandbox and deletes that
sandbox on exit. Its result determines whether ODA is available; Offline
remains the default.

## Credentials

The example connection file contains placeholders only. SAS credentials must
be supplied at runtime through Daytona's secret store, never through an image
layer, committed file, or source-code default. Local runs use `~/.authinfo`;
see [`../../docs/live-sas-run-sheet.md`](../../docs/live-sas-run-sheet.md).
