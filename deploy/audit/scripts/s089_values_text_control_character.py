"""Audit 89: values_text_control_character. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': 'line1\nline2', 'company_q': 'b', 'company_dq': 'c', 'study_id': 'ABC-123'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V007', 'company')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
