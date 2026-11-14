"""Audit 237: pool_idle. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'idle', 'config': {'max_size': 1, 'acquire_timeout': 0.05, 'idle_timeout': 0.01}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['counts']['created']==2,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
