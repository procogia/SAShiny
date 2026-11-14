"""Audit 43: values_choice_static_and_labelled. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/choice', 'today': '2026-11-11', 'values': {'origin': 'USA', 'flag': 'N', 'make': 'Audi'}, 'choices': {'make': ['Acura', 'Audi', 'BMW']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'ORIGIN': 'USA', 'FLAG': "'N'", 'MAKE': 'Audi'}, (language, got)
        assert got['macro_order'] == ['ORIGIN', 'FLAG', 'MAKE'], (language, got)
        assert not got['issues'], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
