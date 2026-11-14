"""Audit 239: pool_busy_choices. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'busy_choices', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['errors'] and all('pool exhausted' in e for e in got['errors']),got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
