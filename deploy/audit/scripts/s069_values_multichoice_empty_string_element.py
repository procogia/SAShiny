"""Audit 69: values_multichoice_empty_string_element. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': [''], 'types': []}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V004', 'origins')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
