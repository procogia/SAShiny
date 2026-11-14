"""Audit 20: contract_s007_bare_not_name. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s007_bare_not_name', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S007', '/inputs/m/choices')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
