"""Audit 351: demo_contract_pharma. Category: demo-integration."""
from client import *

body = {'example': 'pharma/ae_summary.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert not got['issues'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
