# SAShiny (R)

R package for SAShiny. Use an unchanged SAS program as the server of a Shiny app.

> Status: beta (0.2.0). The contract is specified in [`../spec/CONTRACT.md`](../spec/CONTRACT.md).

SAS 9.4, SAS Viya and SAS ODA (OnDemand for Academics) connections are available.
You are responsible for obtaining access to a compatible SAS compiler for your chosen
profile; SAShiny does not provide SAS. Live SAS connections are not yet verified.

```r
pak::pak("procogia/SAShiny/R")
```

## Supported SAS systems and licensing

SAShiny runs programs only on a live SAS system: **SAS 9.4** (IOM or SSH),
**SAS Viya** or **SAS OnDemand for Academics**. There is no offline or
recorded mode. SAS is commercial software. **You are responsible for holding a
valid licence** for the system you connect to (or accepting ODA's terms of
use). Before a run, acknowledge this with one of:

```r
options(SAShiny.license_ack = TRUE)                 # per R session
engine <- sas_connect("oda", license_ack = TRUE)    # per engine
# or set SASHINY_LICENSE_ACK=true for a deployed app
```

## Publish to Posit Connect

```r
# CONNECT_SERVER, CONNECT_API_KEY, SASHINY_SAS_USER and SASHINY_SAS_PASSWORD
# in ~/.Renviron, or a registered rsconnect account.
sas_publish("my-app", title = "Cars explorer", license_ack = TRUE)
```

You can also use the *Publish SAShiny app to Posit Connect* RStudio/Positron
addin, or `sas_app(..., publish = TRUE)`. Credential files (`.authinfo`,
`.Renviron`, `.env`, keys) are never bundled.
