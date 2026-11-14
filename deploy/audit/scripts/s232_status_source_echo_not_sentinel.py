"""Audit 232: status_source_echo_not_sentinel. Category: run-status."""
from client import *

body = {'log': '1  %put NOTE: SASHINY-END run=audit syscc=0;\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'status', body)
        assert got['status']=='error',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
