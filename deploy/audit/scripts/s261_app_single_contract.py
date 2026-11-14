"""Audit 261: app_single_contract. Category: app."""
from client import *

body = {}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'app', body)
        assert got['built'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
