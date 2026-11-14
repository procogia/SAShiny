"""Audit 80: values_numeric_unknown_input. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 1, 'ratio': 0, 'nope': 1}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V011', 'nope')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
