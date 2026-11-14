"""Audit 81: values_regex_ascii_ascii_digits_match. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/regex_ascii', 'today': '2026-11-11', 'values': {'digits': '123', 'word': 'abc'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'DIGITS': '123', 'WORD': 'abc'}, (language, got)
        assert got['macro_order'] == ['DIGITS', 'WORD'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
