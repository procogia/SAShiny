# Examples

Each example is an unchanged SAS program plus its SAShiny sidecar contract.

| Track | Program | Contract | Data | Business case |
|---|---|---|---|---|
| General | [`cars_explorer.sas`](general/cars_explorer.sas) | [`cars_explorer.sashiny.yml`](general/cars_explorer.sashiny.yml) | `SASHELP.CARS` (ships with SAS) | Self-service apps on existing SAS |
| Pharma | [`ae_summary.sas`](pharma/ae_summary.sas) (macro library) | [`ae_summary.sashiny.yml`](pharma/ae_summary.sashiny.yml) | Synthetic ADSL/ADAE in [`pharma/data`](pharma/data) | Interactive review of validated TEAE tables |
| AML | [`cash_aggregation_tuning.sas`](aml/cash_aggregation_tuning.sas) | [`cash_aggregation_tuning.sashiny.yml`](aml/cash_aggregation_tuning.sashiny.yml) | Synthetic transactions in [`aml/data`](aml/data) | Above/below-the-line threshold tuning |
| Forecasting | [`arima_forecast.sas`](forecasting/arima_forecast.sas) (macro library) | [`arima_forecast.sashiny.yml`](forecasting/arima_forecast.sashiny.yml) | Simulated monthly prescriptions in [`forecasting/data`](forecasting/data) | ARIMA / SARIMA demand forecasting with model comparison ([details](forecasting/README.md)) |

All programs also run on their own in SAS 9.4M5+ or SAS Viya. The General and AML programs guard
their standalone defaults with `%if not %symexist(...)`, so the values SAShiny injects take precedence
(CONTRACT.md §9). The Pharma and Forecasting programs are macro libraries whose parameters have
defaults. Forecasting needs SAS/ETS.

The sample data are entirely synthetic. They are regenerated deterministically by the script in each
`data/` folder (`make_data.py`, or `generate_rx_data.py` for Forecasting).

`connections.example.yml` shows the draft connection-profile format with placeholders (ODA, ProCogia Viya, ProCogia SAS 9.4 IOM/SSH, offline).
