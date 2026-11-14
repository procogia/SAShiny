"""Audit 359: demo_lint_forecasting. Category: demo-integration."""
from client import *

body = {'example': 'forecasting/arima_forecast.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert not got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
