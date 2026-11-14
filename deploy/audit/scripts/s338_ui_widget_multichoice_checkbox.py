"""Audit 338: ui_widget_multichoice_checkbox. Category: ui-controls."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'multichoice', 'label': 'X', 'choices': ['a', 'b'], 'widget': 'checkbox'}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert 'mod-x' in got['html'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
