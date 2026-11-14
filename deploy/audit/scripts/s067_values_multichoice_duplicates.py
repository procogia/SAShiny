"""Audit 67: values_multichoice_duplicates. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': ['Asia', 'Asia'], 'types': []}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V008', 'origins')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
