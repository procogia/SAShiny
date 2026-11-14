"""Audit 22: contract_s008_rtf_with_from. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s008_rtf_with_from', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S008', '/outputs/dl')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
