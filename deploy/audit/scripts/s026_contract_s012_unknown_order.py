"""Audit 26: contract_s012_unknown_order. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/s012_unknown_order', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert codes(got) == [('S012', '/ui/order/0')], (language, got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
