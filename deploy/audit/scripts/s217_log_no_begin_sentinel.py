"""Audit 217: log_no_begin_sentinel. Category: collect-fixtures."""
from client import *

body = {'function': 'scope_log', 'args': ['ERROR: session ended', 'program']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got==[],(language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
