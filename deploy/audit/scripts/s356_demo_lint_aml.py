"""Audit 356: demo_lint_aml. Category: demo-integration."""
from client import *

body = {'example': 'aml/cash_aggregation_tuning.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert not got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
