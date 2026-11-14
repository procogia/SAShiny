"""Audit 70: values_multichoice_null_element. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': [None], 'types': []}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V002', 'origins')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
