"""Audit 75: values_numeric_fifteen_digits. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 1, 'ratio': 0.1, 'big': 3.141592653589793}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'MIN_MSRP': '1', 'RATIO_VALUE': '0.1', 'BIG': '3.14159265358979'}, (language, got)
        assert got['macro_order'] == ['MIN_MSRP', 'RATIO_VALUE', 'BIG'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
