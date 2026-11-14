"""Audit 102: multichoice_shape_. Category: value-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'multichoice', 'label': 'X', 'choices': ['a', 'b'], 'optional': True, 'min_selected': 0, 'count_macro': 'n'}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'x': ''}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert codes(got) == [], (language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
