"""Audit 44: values_choice_not_in_static. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/choice', 'today': '2026-11-11', 'values': {'origin': 'Mars', 'flag': 'Yes', 'make': 'Audi'}, 'choices': {'make': ['Audi']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V004', 'flag'), ('V004', 'origin')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
