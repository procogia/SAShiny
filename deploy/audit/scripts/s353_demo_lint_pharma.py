"""Audit 353: demo_lint_pharma. Category: demo-integration."""
from client import *

body = {'example': 'pharma/ae_summary.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'lint', body)
        assert not got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
