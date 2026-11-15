# SAShiny (R)

R package for SAShiny. Use an unchanged SAS program as the server of a Shiny app.

> Status: beta (0.1.6). The contract is specified in [`../spec/CONTRACT.md`](../spec/CONTRACT.md).

SAS 9.4, SAS Viya and SAS ODA (OnDemand for Academics) connections are available.
You are responsible for obtaining access to a compatible SAS compiler for your chosen
profile; SAShiny does not provide SAS. Live SAS connections are not yet verified.

```r
# development version (0.1.6 prepared for CRAN)
pak::pak("procogia/SAShiny/R")
```
