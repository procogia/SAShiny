"""Audit 310: column_selection_order. Category: table-collection."""
from client import *

body = {'function': 'select_columns', 'args': [[{'name': 'Age', 'type': 'numeric', 'label': 'Age label', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], ['name', 'age']]}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert [c['name'] for c in got]==['NAME','Age'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
