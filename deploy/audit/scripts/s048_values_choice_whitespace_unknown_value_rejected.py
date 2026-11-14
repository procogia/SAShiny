"""Audit 48: values_choice_whitespace_unknown_value_rejected. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/choice_whitespace', 'today': '2026-11-11', 'values': {'padded': 'B'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V004', 'padded')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
