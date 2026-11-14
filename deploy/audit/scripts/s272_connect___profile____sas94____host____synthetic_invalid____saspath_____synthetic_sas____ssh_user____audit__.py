"""Audit 272: connect_{'profile': 'sas94', 'host': 'synthetic.invalid', 'saspath': '/synthetic/sas', 'ssh_user': 'audit'}. Category: connection-configuration."""
from client import *

body = {'kwargs': {'profile': 'sas94', 'host': 'synthetic.invalid', 'saspath': '/synthetic/sas', 'ssh_user': 'audit'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'connect', body)
        assert got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
