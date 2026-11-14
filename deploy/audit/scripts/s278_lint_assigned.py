"""Audit 278: lint_assigned. Category: lint."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'price': {'type': 'numeric', 'label': 'P', 'macro': 'MSRP'}}, 'outputs': {'report': {'type': 'log'}}}, 'program': '%let MSRP = 5; %put &MSRP;'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert sorted((i['code'],i['path']) for i in got)==[('L001', '/inputs/price')],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
