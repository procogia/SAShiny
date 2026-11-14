"""Audit 247: fake_sas_slow_submit. Category: engine-lifecycle."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'report': {'type': 'log'}}, 'run': {'timeout_seconds': 1}}, 'scenario': 'slow_submit'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'fake', body)
        assert got['results'][0]['status']=='error',got
        assert all(got['closed_before']),got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
