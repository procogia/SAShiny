"""Audit 343: sample_control_id_collision. Category: ui-identifiers."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'dataset': {'type': 'dataset', 'label': 'Upload', 'target': 'work.data', 'sample': 'sample.csv'}, 'dataset__sample': {'type': 'text', 'label': 'Named like generated input', 'optional': True}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        assert got['html'].count('id="mod-dataset__sample"')==1,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
