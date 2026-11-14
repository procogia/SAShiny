"""Audit 267: connect_oda_eu1. Category: connection-configuration."""
from client import *

body = {'kwargs': {'profile': 'oda', 'region': 'eu1', 'java': '/usr/bin/java'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'connect', body)
        assert got['iomport']==8591 and got['authkey']=='oda',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
