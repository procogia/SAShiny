"""Audit 357: demo_contract_forecasting. Category: demo-integration."""
from client import *

body = {'example': 'forecasting/arima_forecast.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert not got['issues'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
