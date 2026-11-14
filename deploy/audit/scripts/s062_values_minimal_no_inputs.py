"""Audit 62: values_minimal_no_inputs. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/minimal', 'today': '2026-11-11', 'values': {}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {}, (language, got)
        assert got['macro_order'] == [], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
