"""Audit 27: contract_s013_program_missing. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s013_program_missing', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S013', '/program')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
