"""Audit 318: dynamic_choices_validation. Category: dynamic-choices."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'pick': {'type': 'choice', 'label': 'Pick', 'choices_from': {'dataset': 'work.c', 'value_column': 'v'}}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'pick': 'b'}, 'choices': {'pick': ['a']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got)==[('V004','pick')],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
