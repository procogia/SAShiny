# Deploying SAShiny apps (Python)

`sashiny.deploy.deploy()` turns an app directory into deployment files for one hosting platform
(spec §6.8). It works in two steps:

1. **Generate** (offline). It writes the bundle (your app without credential files) and the
   platform's files: a `Dockerfile`, a template, SQL and a step-by-step guide.
2. **Apply** (optional, `apply=True`). It runs the platform CLI with the commands the guide lists.

Programs run only on a live, licensed SAS system. Every deployment needs `license_ack=True`: you
confirm that the deployed app runs programs only on a SAS system you are licensed to use.

```python
from sashiny import deploy as d

print([t.id for t in d.targets()])
viya = {"name": "viya", "method": "http", "url": "https://viya.example.com"}
res = d.deploy("my-app", "container", "out", viya, license_ack=True)
print(res.files, res.endpoints, res.secrets)
print(d.doctor("azure_container_apps"))  # missing tools or variables, by name only
```

## The connection profile

The profile says how the deployed app reaches SAS. It decides the egress endpoints, whether Java 17
is needed (IOM: ODA and SAS 9.4) and the runtime environment variables. Secrets appear by name only
(`SASHINY_SAS_USER`, `SASHINY_SAS_PASSWORD`); their values come from the platform's secret store.

A profile with `requires_vpn: true` fails unless you pass the target's private-network option. You
confirm that the network route exists; SAShiny does not create it.

## Targets

Each target that puts a load balancer in front of the app enables WebSockets and session affinity,
which Shiny needs. Each generated guide lists the exact commands, with `<...>` placeholders.

| Target | Spec | When to use it | Apply runs | Custom domain |
|---|---|---|---|---|
| `container` | §6.8 | Any container host (Kubernetes, Cloud Run, Docker) | nothing | your host |
| `azure_container_apps` | §6.8.1 | Azure; Key Vault secrets; optional VNet (`infrastructure_subnet_id`) | `az acr build`, `az deployment group create` | CNAME and `asuid` TXT, then `az containerapp hostname bind` |
| `aws_ecs_express` | §6.8.2 | AWS; Fargate behind an ALB with stickiness and a 1 h idle timeout | `docker build/push`, `aws cloudformation deploy` | ACM certificate and a Route 53 alias |
| `snowflake_spcs` | §6.8.3 | Snowflake sign-in in front of your own container | `snow sql`, `snow spcs image-registry login`, `docker push` | Snowflake endpoint URL |
| `posit_snowflake` | §6.8.4 | Clients licensed for Posit Team in Snowflake | `sashiny.publish()` | Posit Connect |
| `streamlit_snowflake` | §6.8.5 | A Streamlit front end in Snowflake (Viya only) | `snow sql`, `snow stage copy` | Snowsight URL |
| `databricks_apps` | §6.8.6 | Databricks workspaces (Viya only) | `databricks sync`, `databricks apps deploy` | Databricks app URL |

SPCS ingress supports WebSockets and closes idle connections after 90 seconds; Shiny's heartbeat
keeps them open. Snowflake does not document session affinity, so the default is one instance.

The Streamlit in Snowflake and Databricks Apps runtimes install Python packages only. They cannot
provide Java, so they accept only SAS Viya (http) profiles. There is no R equivalent (issue #116).

The container images target `linux/amd64`. On an ARM machine (Apple silicon), build with
`docker build --platform linux/amd64 -t my-app .`: some Python packages have no ARM Linux wheels
and the image has no compiler. `deploy/check-container-images.sh` builds and smoke-tests both
images from a checkout.

## Comparison

| Target | Languages | SAS profiles | User sign-in | Cost model |
|---|---|---|---|---|
| `container` | R, Python | all | your host | your host |
| `azure_container_apps` | R, Python | all | Azure ingress (add Easy Auth) | per replica-second |
| `aws_ecs_express` | R, Python | all | ALB (add Cognito or OIDC) | Fargate task-hours plus load balancer |
| `snowflake_spcs` | R, Python | all | Snowflake | compute pool node-hours |
| `posit_snowflake` | R, Python | all (IOM needs Java in the Connect image) | Posit Connect | Posit Team licence plus Snowflake compute |
| `streamlit_snowflake` | Python | Viya | Snowflake | compute pool node-hours plus warehouse |
| `databricks_apps` | Python | Viya | Databricks | app compute-hours |

A target is "generated only" until a real deployment is recorded in
[`docs/deploy-verification.md`](../../docs/deploy-verification.md).
