"""Audit 115: daterange_shape_[None, None]. Category: value-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'daterange', 'label': 'X', 'optional': True}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'x': [None, None]}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [('V002', 'x')], (language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
