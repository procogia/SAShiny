"""Audit 349: demo_ui_general. Category: demo-integration."""
from client import *

body = {'example': 'general/cars_explorer.sashiny.yml'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'mod-run' in got['html'] and 'mod-status' in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
