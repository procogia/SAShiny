"""Audit 86: values_text_unicode. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': 'CafÃ© ÃœnÃ¯code', 'company_q': 'æ—¥æœ¬', 'company_dq': 'x', 'study_id': 'ABC-000'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'COMPANY': 'CafÃ© ÃœnÃ¯code', 'COMPANY_Q': "'æ—¥æœ¬'", 'COMPANY_DQ': '"x"', 'STUDY_ID': 'ABC-000'}, (language, got)
        assert got['macro_order'] == ['COMPANY', 'COMPANY_Q', 'COMPANY_DQ', 'STUDY_ID'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
