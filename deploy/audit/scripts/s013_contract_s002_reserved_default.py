"""Audit 13: contract_s002_reserved_default. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s002_reserved_default', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S002', '/inputs/sysx')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
