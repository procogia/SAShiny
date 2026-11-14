"""Audit 18: contract_s005_duplicate_choices. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s005_duplicate_choices', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S005', '/inputs/c/choices')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
