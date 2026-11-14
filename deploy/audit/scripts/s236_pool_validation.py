"""Audit 236: pool_validation. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'validation', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['counts']['created']==1,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
