"""Audit 199: mock_upload_empty_file. Category: mock-content-validation."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'data': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}}, 'outputs': {'report': {'type': 'log'}}}, 'files': [{'name': 'input.csv', 'text': ''}], 'uploads': {'data': 'input.csv'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'mock', body)
        assert got['status']=='error' and got['metadata']['issues'][0]['code']=='V014',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
