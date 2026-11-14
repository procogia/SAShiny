"""Audit 354: demo_contract_aml. Category: demo-integration."""
from client import *

body = {'example': 'aml/cash_aggregation_tuning.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert not got['issues'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
