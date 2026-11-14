"""Audit 238: pool_factory_error. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'factory_error', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['results'][0]['status']=='error',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
