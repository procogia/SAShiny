"""Audit 100: daterange_single_max_bound. Category: contract-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'daterange', 'label': 'X', 'max': '2026-01-01'}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [], (language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
