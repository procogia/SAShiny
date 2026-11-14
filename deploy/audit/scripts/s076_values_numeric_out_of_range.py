"""Audit 76: values_numeric_out_of_range. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 200001, 'ratio': 2}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V003', 'min_msrp'), ('V003', 'ratio')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
