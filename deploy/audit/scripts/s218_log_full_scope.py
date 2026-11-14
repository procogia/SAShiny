"""Audit 218: log_full_scope. Category: collect-fixtures."""
from client import *

body = {'function': 'scope_log', 'args': ['NOTE: a\nWARNING: b\nplain', 'full']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got==[{'level': 'note', 'text': 'NOTE: a'}, {'level': 'warning', 'text': 'WARNING: b'}, {'level': 'text', 'text': 'plain'}],(language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
