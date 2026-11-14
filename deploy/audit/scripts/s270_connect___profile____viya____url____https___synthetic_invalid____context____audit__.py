"""Audit 270: connect_{'profile': 'viya', 'url': 'https://synthetic.invalid', 'context': 'audit'}. Category: connection-configuration."""
from client import *

body = {'kwargs': {'profile': 'viya', 'url': 'https://synthetic.invalid', 'context': 'audit'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'connect', body)
        assert got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
