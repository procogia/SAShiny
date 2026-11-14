"""Audit 229: status_syscc_0. Category: run-status."""
from client import *

body = {'log': 'NOTE: SASHINY-END run=audit syscc=0\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='success',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
