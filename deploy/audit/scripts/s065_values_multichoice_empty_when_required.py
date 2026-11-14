"""Audit 65: values_multichoice_empty_when_required. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': [], 'types': []}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V001', 'origins')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
