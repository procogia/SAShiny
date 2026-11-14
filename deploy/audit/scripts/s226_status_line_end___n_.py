"""Audit 226: status_line_end_'\n'. Category: run-status."""
from client import *

body = {'log': 'NOTE: hi\nERROR: bad\nNOTE: SASHINY-END run=audit syscc=0\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='error',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
