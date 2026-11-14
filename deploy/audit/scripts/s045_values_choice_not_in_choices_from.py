"""Audit 45: values_choice_not_in_choices_from. Category: value-fixtures."""
from client import *

body = {'fixture': 'contracts/valid/choice', 'today': '2026-11-11', 'values': {'origin': 'USA', 'flag': 'Y', 'make': 'Tesla'}, 'choices': {'make': ['Acura', 'Audi']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V004', 'make')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
