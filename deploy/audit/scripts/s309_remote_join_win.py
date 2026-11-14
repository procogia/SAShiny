"""Audit 309: remote_join_win. Category: remote-paths."""
from client import *

body = {'function': 'join_remote', 'args': ['C:\\synthetic\\work\\', 'out.csv']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got=='C:\\synthetic\\work\\out.csv',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
