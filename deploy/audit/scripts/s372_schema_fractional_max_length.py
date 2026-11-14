"""Audit 372: schema_fractional_max_length. Category: schema-precision."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'text', 'label': 'X', 'max_length': 1.000001}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert any(i['code']=='E000' for i in got['issues']),got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
