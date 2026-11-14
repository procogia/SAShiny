"""Audit 259: ui_layout_sidebar. Category: ui-options."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'report': {'type': 'log'}}, 'ui': {'layout': 'sidebar'}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'mod-run' in got['html'] and 'mod-out_report' in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
