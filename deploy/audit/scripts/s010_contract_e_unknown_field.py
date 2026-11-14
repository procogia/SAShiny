"""Audit 10: contract_e_unknown_field. Category: contract-fixtures."""
from client import *

body = {'fixture': 'contracts/invalid/e_unknown_field', 'today': '2026-11-11'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        wanted = [('E000', '/inputs/n')]
        found = codes(got)
        assert found and all(c == 'E000' for c,p in found), (language, found)
        assert all(any(gp.startswith(p) or p.startswith(gp) for c,gp in found) for _,p in wanted), (language, wanted, found)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
