"""Audit 12: contract_s001_duplicate_macro. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s001_duplicate_macro', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S001', '/inputs/b')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
