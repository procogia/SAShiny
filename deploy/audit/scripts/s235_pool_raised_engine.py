"""Audit 235: pool_raised_engine. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'raised_engine', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['counts']['created']==2 and got['counts']['closed']==2,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
