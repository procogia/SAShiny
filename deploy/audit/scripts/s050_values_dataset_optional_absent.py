"""Audit 50: values_dataset_optional_absent. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/dataset', 'today': '2026-11-11', 'values': {}, 'uploads': {'adsl': True}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'EXTRA_DS': ''}, (language, got)
        assert got['macro_order'] == ['EXTRA_DS'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
