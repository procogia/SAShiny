"""Audit 109: daterange_shape_['bad', None]. Category: value-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'daterange', 'label': 'X', 'optional': True}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'x': ['bad', None]}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V009', 'x')], (language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
