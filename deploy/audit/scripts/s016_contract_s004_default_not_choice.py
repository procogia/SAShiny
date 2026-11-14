"""Audit 16: contract_s004_default_not_choice. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s004_default_not_choice', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S004', '/inputs/c/default')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
