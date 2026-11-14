"""Audit 79: values_numeric_missing_required. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'ratio': 0}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V001', 'min_msrp')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
