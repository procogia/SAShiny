"""Audit 260: ui_override. Category: ui-options."""
from client import *

body = {'override': True}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'audit override' in got['html'] and 'mod-run' not in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
