"""Audit 15: contract_s003_min_gt_max. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s003_min_gt_max', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S003', '/inputs/n')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
