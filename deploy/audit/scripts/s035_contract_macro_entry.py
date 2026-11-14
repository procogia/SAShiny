"""Audit 35: contract_macro_entry. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/macro_entry', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
