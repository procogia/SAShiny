"""Audit 331: ui_control_text. Category: ui-controls."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'text', 'label': 'text'}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'mod-x' in got['html'] and 'mod-run' in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
