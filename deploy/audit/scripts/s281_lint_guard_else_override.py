"""Audit 281: lint_guard_else_override. Category: lint."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'price': {'type': 'numeric', 'label': 'P', 'macro': 'MSRP'}}, 'outputs': {'report': {'type': 'log'}}}, 'program': '%if not %symexist(MSRP) %then %do; %let MSRP=5; %end;\n%let MSRP=99;\n%put &MSRP;'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert ('L001','/inputs/price') in [(i['code'],i['path']) for i in got],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
