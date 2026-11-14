"""Audit 52: values_dates_all_renders. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dates', 'today': '2026-11-11', 'values': {'cutoff': '2026-11-11', 'as_date9': '2025-01-01', 'as_iso': '2025-06-30', 'as_num': '1959-12-31', 'period': ['2026-01-01', '2026-06-30'], 'window': ['1960-01-01', '2026-11-11']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'CUTOFF': "'11NOV2026'd", 'AS_DATE9': '01JAN2025', 'AS_ISO': '2025-06-30', 'AS_NUM': '-1', 'PERIOD_START': "'01JAN2026'd", 'PERIOD_END': "'30JUN2026'd", 'WIN_FROM': '0', 'WIN_TO': '24421'}, (language, got)
        assert got['macro_order'] == ['CUTOFF', 'AS_DATE9', 'AS_ISO', 'AS_NUM', 'PERIOD_START', 'PERIOD_END', 'WIN_FROM', 'WIN_TO'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
