"""Audit 51: values_dataset_required_missing. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dataset', 'today': '2026-11-11', 'values': {}, 'uploads': {'extra': True}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V001', 'adsl')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
