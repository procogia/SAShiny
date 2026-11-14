"""Audit 78: values_numeric_wrong_type. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': '100', 'ratio': True}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V002', 'min_msrp'), ('V002', 'ratio')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
