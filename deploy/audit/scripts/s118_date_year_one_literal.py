"""Audit 118: date_year_one_literal. Category: value-boundaries."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'date', 'label': 'X', 'render': 'literal'}}, 'outputs': {'report': {'type': 'log'}}}, 'values': {'x': '0001-01-01'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'values', body)
        assert got['macros'] == {'X':"'01JAN0001'd"}, (language,got)
        assert not got['issues']
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
