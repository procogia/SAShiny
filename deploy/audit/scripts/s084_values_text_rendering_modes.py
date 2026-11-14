"""Audit 84: values_text_rendering_modes. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': "  O'Brien & Co  ", 'company_q': "O'Brien & Co", 'company_dq': 'Say "hi" %nrstr(x)', 'study_id': 'ABC-123'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'COMPANY': "O'Brien & Co", 'COMPANY_Q': "'O''Brien & Co'", 'COMPANY_DQ': '"Say ""hi"" %nrstr(x)"', 'STUDY_ID': 'ABC-123'}, (language, got)
        assert got['macro_order'] == ['COMPANY', 'COMPANY_Q', 'COMPANY_DQ', 'STUDY_ID'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
