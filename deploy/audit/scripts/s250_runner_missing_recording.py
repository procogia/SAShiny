"""Audit 250: runner_missing_recording. Category: engine-runner."""
from client import *

body = {'by_path': True}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'runner', body)
        assert got['status']=='success',got
        assert got['metadata']['recording']=='missing',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
