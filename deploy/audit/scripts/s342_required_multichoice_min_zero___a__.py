"""Audit 342: required_multichoice_min_zero_['a']. Category: value-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'multichoice', 'label': 'X', 'choices': ['a'], 'min_selected': 0}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'x': ['a']}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert not got['issues'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
