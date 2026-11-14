"""Audit 355: demo_ui_aml. Category: demo-integration."""
from client import *

body = {'example': 'aml/cash_aggregation_tuning.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'mod-run' in got['html'] and 'mod-status' in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
