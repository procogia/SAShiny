# SAShiny (Python)

Python library for SAShiny. Use an unchanged SAS program as the server of a Shiny for Python app.

> Status: beta (0.1.7). The contract is specified in
> [`spec/CONTRACT.md`](https://github.com/procogia/SAShiny/blob/main/spec/CONTRACT.md).

SAS 9.4, SAS Viya and SAS ODA (OnDemand for Academics) connections are available.
You are responsible for obtaining access to a compatible SAS compiler for your chosen
profile; SAShiny does not provide SAS. Live SAS connections are not yet verified.

```sh
# released on PyPI
uv pip install sashiny
# optional extras: sashiny[shiny], sashiny[saspy], sashiny[plotnine], sashiny[matplotlib], sashiny[plotly]
```

SAS is a registered trademark of SAS Institute Inc. Shiny is a registered trademark of Posit
Software, PBC. This project is not affiliated with or endorsed by either company.
