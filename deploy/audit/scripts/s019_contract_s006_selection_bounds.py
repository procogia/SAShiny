"""Audit 19: contract_s006_selection_bounds. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s006_selection_bounds', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S006', '/inputs/m')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
