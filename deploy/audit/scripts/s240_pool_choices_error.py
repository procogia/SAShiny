"""Audit 240: pool_choices_error. Category: pool-lifecycle."""
from client import *

body = {'scenario': 'choices_error', 'config': {'max_size': 1, 'acquire_timeout': 0.05}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'pool', body)
        assert got['sessions_before_close']==0,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
