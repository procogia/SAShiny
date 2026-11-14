"""Audit 251: mock_recording_replay. Category: recording."""
from client import *

body = {'recording': {'status': 'warning', 'log': 'WARNING: synthetic', 'outputs': {'table': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'mock', body)
        assert got['status']=='warning',got
        assert got['outputs']=={'table': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}},got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
