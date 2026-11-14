"""Audit 271: connect_{'profile': 'sas94', 'host': 'synthetic.invalid', 'port': 8592, 'java': '/usr/bin/java'}. Category: connection-configuration."""
from client import *

body = {'kwargs': {'profile': 'sas94', 'host': 'synthetic.invalid', 'port': 8592, 'java': '/usr/bin/java'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'connect', body)
        assert got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
