"""Audit 231: status_syscc_8. Category: run-status."""
from client import *

body = {'log': 'NOTE: SASHINY-END run=audit syscc=8\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='error',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
