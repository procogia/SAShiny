"""Audit 64: values_multichoice_empty_allowed_and_optional_absent. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/multichoice', 'today': '2026-11-11', 'values': {'origins': ['Europe'], 'types': []}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'ORIGINS': "'Europe'", 'N_ORIGINS': '1', 'TYPES': '', 'ARMS': '', 'N_ARMS': '0'}, (language, got)
        assert got['macro_order'] == ['ORIGINS', 'N_ORIGINS', 'TYPES', 'ARMS', 'N_ARMS'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
