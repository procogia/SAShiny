"""Audit 82: values_regex_ascii_arabic_indic_digit_rejected. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/regex_ascii', 'today': '2026-11-11', 'values': {'digits': '١', 'word': 'abc'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V005', 'digits')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
