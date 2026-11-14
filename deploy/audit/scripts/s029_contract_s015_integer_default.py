"""Audit 29: contract_s015_integer_default. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s015_integer_default', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S004', '/inputs/n/default'), ('S015', '/inputs/n/default')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
