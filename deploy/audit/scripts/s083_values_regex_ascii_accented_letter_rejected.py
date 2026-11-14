"""Audit 83: values_regex_ascii_accented_letter_rejected. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/regex_ascii', 'today': '2026-11-11', 'values': {'digits': '123', 'word': 'é'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V005', 'word')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
