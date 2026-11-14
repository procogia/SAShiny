"""Audit 230: status_syscc_4. Category: run-status."""
from client import *

body = {'log': 'NOTE: SASHINY-END run=audit syscc=4\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='warning',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
