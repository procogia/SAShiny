"""Audit 17: contract_s004_default_out_of_range. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s004_default_out_of_range', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S004', '/inputs/n/default')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
