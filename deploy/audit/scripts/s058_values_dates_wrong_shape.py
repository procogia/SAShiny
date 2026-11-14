"""Audit 58: values_dates_wrong_shape. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dates', 'today': '2026-11-11', 'values': {'cutoff': '2026-01-01', 'period': '2026-01-01'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V002', 'period')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
