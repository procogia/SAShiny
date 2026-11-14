"""Audit 53: values_dates_optional_absent. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dates', 'today': '2026-11-11', 'values': {'cutoff': '2020-01-01', 'period': ['2026-02-28', '2026-02-28']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'CUTOFF': "'01JAN2020'd", 'AS_DATE9': '', 'AS_ISO': '', 'AS_NUM': '', 'PERIOD_START': "'28FEB2026'd", 'PERIOD_END': "'28FEB2026'd", 'WIN_FROM': '', 'WIN_TO': ''}, (language, got)
        assert got['macro_order'] == ['CUTOFF', 'AS_DATE9', 'AS_ISO', 'AS_NUM', 'PERIOD_START', 'PERIOD_END', 'WIN_FROM', 'WIN_TO'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
