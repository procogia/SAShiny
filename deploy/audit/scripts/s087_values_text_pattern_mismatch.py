"""Audit 87: values_text_pattern_mismatch. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': 'a', 'company_q': 'b', 'company_dq': 'c', 'study_id': 'abc-123'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V005', 'study_id')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
