"""Audit 61: values_macro_entry_defaults. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/macro_entry', 'today': '2026-11-11', 'values': {'arm': 'Drug A', 'min_pct': 5}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'ARM': "'Drug A'", 'MIN_PCT': '5'}, (language, got)
        assert got['macro_order'] == ['ARM', 'MIN_PCT'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
