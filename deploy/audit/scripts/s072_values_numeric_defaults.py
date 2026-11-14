"""Audit 72: values_numeric_defaults. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/numeric', 'today': '2026-11-11', 'values': {'min_msrp': 20000, 'ratio': 0.5}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'MIN_MSRP': '20000', 'RATIO_VALUE': '0.5', 'BIG': ''}, (language, got)
        assert got['macro_order'] == ['MIN_MSRP', 'RATIO_VALUE', 'BIG'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
