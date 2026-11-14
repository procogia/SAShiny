"""Audit 28: contract_s014_lookahead_pattern. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s014_lookahead_pattern', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S014', '/inputs/t/pattern')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
