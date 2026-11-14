"""Audit 24: contract_s010_duplicate_target. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s010_duplicate_target', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S010', '/inputs/b/target')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
