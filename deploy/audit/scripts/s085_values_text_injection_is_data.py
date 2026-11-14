"""Audit 85: values_text_injection_is_data. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/text', 'today': '2026-11-11', 'values': {'company': "'; endsas; %sysexec rm -rf /; '", 'company_q': '&sysuserid', 'company_dq': 'x', 'study_id': 'XYZ-999'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'COMPANY': "'; endsas; %sysexec rm -rf /; '", 'COMPANY_Q': "'&sysuserid'", 'COMPANY_DQ': '"x"', 'STUDY_ID': 'XYZ-999'}, (language, got)
        assert got['macro_order'] == ['COMPANY', 'COMPANY_Q', 'COMPANY_DQ', 'STUDY_ID'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
