"""Audit 241: pool_close_reopen. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'close_reopen', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['counts']['created']==1,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
