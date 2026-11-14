"""Audit 25: contract_s011_id_collision. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s011_id_collision', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S011', '/outputs/log')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
