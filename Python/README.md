# SAShiny (Python) <img src="https://raw.githubusercontent.com/procogia/SAShiny/main/R/man/figures/logo.png" align="right" height="139" alt="SAShiny logo: a crescent moon" />

*Your SAS and Shiny programs, radiant as the moon.*
Pronounced like *Sashini*, "radiant as the moon": SAS does the analysis and Shiny makes it shine.

Python library for SAShiny. Use an unchanged SAS program as the server of a Shiny for Python app.

> Status: beta (0.3.0). The contract is specified in
> [`spec/CONTRACT.md`](https://github.com/procogia/SAShiny/blob/main/spec/CONTRACT.md).

SAS 9.4, SAS Viya and SAS ODA (OnDemand for Academics) connections are available.
You are responsible for obtaining access to a compatible SAS compiler for your chosen
profile; SAShiny does not provide SAS. Live SAS connections are not yet verified.

```sh
# released on PyPI
uv pip install sashiny
# optional extras: sashiny[shiny], sashiny[saspy], sashiny[plotnine], sashiny[matplotlib], sashiny[plotly],
# sashiny[streamlit]
```

## Deploy

`sashiny.deploy.deploy()` generates deployment files for containers, Azure Container Apps,
Amazon ECS, Snowflake (SPCS, Posit Team, Streamlit), and Databricks Apps. See
[docs/deployment.md](https://github.com/procogia/SAShiny/blob/main/Python/docs/deployment.md).

## Streamlit front end

`sashiny.streamlit_app.streamlit_app` renders the same contracts as a Streamlit app (spec §6.9),
with the same value validation and SAS wrapper as the Shiny modules. There is no R equivalent.

```python
# streamlit_app.py; run with: streamlit run streamlit_app.py
import sashiny
from sashiny.streamlit_app import streamlit_app

streamlit_app(["cars_explorer.sashiny.yml"], sashiny.connect_from_env)
```

## Toggle between SAS graphs and SAShiny charts

A paired output shows the original SAS graph and a SAShiny chart in one card, with a toggle
in the browser (spec §8.6). Add a `chart:` block to a `plot` output, or `sas_plot: <k>` to a
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

```python
sashiny.app([path], engine, chart_view="sas")  # start on the SAS graphs
sashiny.app([path], engine, chart_view={"price_vs_mpg": "sas"})  # per output
sashiny.app([path], engine, chart_toggle=False)  # hide the toggles
```

SAS is a registered trademark of SAS Institute Inc. Shiny is a registered trademark of Posit
Software, PBC. This project is not affiliated with or endorsed by either company.
