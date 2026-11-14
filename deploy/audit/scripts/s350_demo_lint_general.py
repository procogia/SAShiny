"""Audit 350: demo_lint_general. Category: demo-integration."""
from client import *

body = {'example': 'general/cars_explorer.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert not got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
