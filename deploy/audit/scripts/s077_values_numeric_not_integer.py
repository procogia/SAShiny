"""Audit 77: values_numeric_not_integer. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 1.5, 'ratio': 0}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V012', 'min_msrp')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
