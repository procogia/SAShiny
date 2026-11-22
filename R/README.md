# SAShiny (R) <img src="man/figures/logo.png" align="right" height="139" alt="SAShiny logo: a crescent moon" />

*Your SAS and Shiny programs, radiant as the moon.*
Pronounced like *Sashini*, "radiant as the moon": SAS does the analysis and Shiny makes it shine.

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
**SAS Viya** or **SAS OnDemand for Academics**. SAS is commercial software. **You are responsible for holding a
valid licence** for the system you connect to (or accepting ODA's terms of
use). Before a run, acknowledge this with one of:

```r
options(SAShiny.license_ack = TRUE)                 # per R session
engine <- sas_connect(sas_oda(), license_ack = TRUE)    # per engine
# or set SASHINY_LICENSE_ACK=true for a deployed app
```

Two more engines are accepted (spec section 6.6):

* `sas_replay(dir)` replays recordings of runs made on a licensed SAS system,
  for offline demos. A recording is replayed only with its SAS version,
  recording time and the SHA-256 of the contract and program it was made from
  (matching the files on disk); otherwise it is refused with the reason.
  Replayed results say so in the status text ("Replayed from
  9.04.01M0P061913, recorded ..."). Write recordings with `sas_record()`.
* Your own engine class, registered with
  `sas_register_engine("my_engine", license_ack = TRUE, description = "...")`.
  It MUST run every program on a live SAS system you are licensed to use, and
  returns results built with `sas_engine_result()`.

## Publish to Posit Connect

```r
# CONNECT_SERVER, CONNECT_API_KEY, SASHINY_SAS_USER and SASHINY_SAS_PASSWORD
# in ~/.Renviron, or a registered rsconnect account.
sas_publish("my-app", title = "Cars explorer", license_ack = TRUE)
```

You can also use the *Publish SAShiny app to Posit Connect* RStudio/Positron
addin, or `sas_app(..., publish = TRUE)`. Credential files (`.authinfo`,
`.Renviron`, `.env`, keys) are never bundled.

## Toggle between SAS graphs and SAShiny charts

A paired output shows the original SAS graph and a SAShiny chart in one card, with a toggle
in the browser (spec section 8.6). Add a `chart:` block to a `plot` output, or `sas_plot: <k>` to a
`chart` output:

```yaml
outputs:
  price_vs_mpg:
    type: plot
    select: 1                 # the SAS graph shown by "SAS graph"
    chart:                    # the SAShiny chart shown by "SAShiny chart"
      from: work.cars_filtered
      spec: {kind: scatter, x: mpg_city, y: msrp, color: origin}
```

Each card has its own toggle and the module has one that switches them all. The default view is the
SAShiny chart; both settings are code arguments:

```r
sas_app(list(path), engine, chart_view = "sas")                 # start on the SAS graphs
sas_app(list(path), engine, chart_view = list(price_vs_mpg = "sas")) # per output
sas_app(list(path), engine, chart_toggle = FALSE)               # hide the toggles
```
