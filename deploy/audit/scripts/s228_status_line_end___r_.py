"""Audit 228: status_line_end_'\r'. Category: run-status."""
from client import *

body = {'log': 'NOTE: hi\rERROR: bad\rNOTE: SASHINY-END run=audit syscc=0\r'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='error',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
