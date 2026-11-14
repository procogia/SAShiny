"""Audit 56: values_dates_year_zero. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dates', 'today': '2026-11-11', 'values': {'cutoff': '0000-01-01', 'period': ['2026-01-01', '2026-01-02']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V009', 'cutoff')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
