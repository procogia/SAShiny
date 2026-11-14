"""Audit 74: values_numeric_small_and_negative_zero. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 0, 'ratio': -0.0, 'big': 1.5e-07}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'MIN_MSRP': '0', 'RATIO_VALUE': '0', 'BIG': '1.5E-07'}, (language, got)
        assert got['macro_order'] == ['MIN_MSRP', 'RATIO_VALUE', 'BIG'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
