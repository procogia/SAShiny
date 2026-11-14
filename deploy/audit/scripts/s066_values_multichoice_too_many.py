"""Audit 66: values_multichoice_too_many. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': ['Asia'], 'types': ['SUV', 'Sedan', 'Wagon']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V008', 'types')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
