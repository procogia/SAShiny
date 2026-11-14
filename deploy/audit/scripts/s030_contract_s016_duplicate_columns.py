"""Audit 30: contract_s016_duplicate_columns. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s016_duplicate_columns', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S016', '/inputs/d/columns')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
