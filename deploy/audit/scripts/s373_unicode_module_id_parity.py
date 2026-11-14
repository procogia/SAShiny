"""Audit 373: unicode_module_id_parity. Category: app."""
from client import *

body = {'names': ['İstanbul.sas']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'module_id', body)
        assert got==['i_stanbul'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
