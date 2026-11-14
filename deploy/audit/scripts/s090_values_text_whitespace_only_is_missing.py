"""Audit 90: values_text_whitespace_only_is_missing. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': '   ', 'company_q': 'b', 'company_dq': 'c', 'study_id': 'ABC-123'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V001', 'company')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
