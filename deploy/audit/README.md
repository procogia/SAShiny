# SAShiny two-container audit (Docker)

This is Igor's two-VM audit, containerized: a **server** container builds the SAShiny R package and
Python wheel and serves the synthetic operation API + observable Shiny apps; a **client** container
runs the 382-script suite against it over a shared network. No live SAS — the audit uses the
mock/fake engine only (`SASHINY_LIVE=0`).

## Layout

| Path | Purpose |
|---|---|
| `Dockerfile.server` | R + Python + Java 17 + saspy + SAShiny package + API (:8000) + Shiny apps (:8001–8003) |
| `Dockerfile.client` | httpx/websockets/playwright + the harness + `run_suite.py` |
| `docker-compose.yml` | `server` + `client` on a shared network; results mounted to `./results` |
| `scripts/` | 382 independently executable test scripts (one per case) |
| `api.py`, `ops_py.py`, `ops_r.R` | the synthetic operation API and its R/Python dispatchers |
| `start_server.py` | starts the API + Shiny apps, records PIDs |
| `run_suite.py` | runs every manifest script, writes a per-case JSONL ledger |

## Run

```sh
# From the repository root:
docker compose -f deploy/audit/docker-compose.yml up --build
```

The client waits for the server's `/health`, then runs the full suite. Results land in
`deploy/audit/results/` (the `docker-summary.json` and `docker.jsonl` ledger). The client's exit code
is **not** the verdict — inspect the summary and JSONL, as expected exceptions are asserted explicitly
and failed assertions are not automatically GitHub issues.

## Run a single case

```sh
docker compose -f deploy/audit/docker-compose.yml run --rm client \
  sh -c 'AUDIT_CASE_ID=s097 /tmp/client-env/bin/python scripts/s097_date_single_min_bound.py'
```

## Run without Docker (host fallback)

The harness also runs directly on a host with R, Python and uv installed:

```sh
# Server (one terminal): install the package, then serve
cd deploy/audit
sh bootstrap.sh            # clones the repo, installs R + Python deps, builds the wheel
python start_server.py     # API :8000, Shiny :8001-8003

# Client (another terminal):
uv venv /tmp/client-env && uv pip install --python /tmp/client-env/bin/python httpx websockets pillow pytest playwright
export AUDIT_API=http://localhost:8000
/tmp/client-env/bin/python run_suite.py --label host
```

## The two app-helper cases (s381, s382)

`s381`/`s382` drive the real app-helper server (`app_probe.py`/`app_probe.R`) on ports 8004/8005,
which `start_server.py` does not start (they are separate processes, as in the original Daytona
workflow). To run them, start the probes in the server container first:

```sh
docker compose -f deploy/audit/docker-compose.yml exec server sh -c \
  '/tmp/SAShiny/Python/.venv/bin/python -m shiny run /tmp/audit/app_probe.py --host 0.0.0.0 --port 8004 &'
docker compose -f deploy/audit/docker-compose.yml exec server sh -c \
  'Rscript -e "shiny::runApp(\"/tmp/audit/app_probe.R\", host=\"0.0.0.0\", port=8005, launch.browser=FALSE)" &'
```

`app_wire.py` derives the probe hosts from `AUDIT_API` (Daytona preview format); for Docker, set
`AUDIT_APP_PROBE_PYTHON`/`AUDIT_APP_PROBE_R` explicitly and adjust `app_wire.py` accordingly.

## Safety

- No credentials, private datasets or authinfo files are uploaded; all inputs/outputs are synthetic.
- `file_issues.py` is the explicit GitHub reporting step and is not run as part of ordinary testing.
- Destroy the containers when finished (`docker compose ... down`).