"""Audit 46: values_choice_whitespace_padded_value_preserved. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/choice_whitespace', 'today': '2026-11-11', 'values': {'padded': ' A '}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'PADDED': ' A '}, (language, got)
        assert got['macro_order'] == ['PADDED'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
