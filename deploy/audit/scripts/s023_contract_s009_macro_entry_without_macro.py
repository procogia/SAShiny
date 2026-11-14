"""Audit 23: contract_s009_macro_entry_without_macro. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s009_macro_entry_without_macro', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S009', '/run')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
