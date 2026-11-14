"""Audit 202: mock_upload_header_only. Category: mock-content-validation."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'data': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}}, 'outputs': {'report': {'type': 'log'}}}, 'files': [{'name': 'input.csv', 'text': 'age,day\n'}], 'uploads': {'data': 'input.csv'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'mock', body)
        assert got['status']=='success',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
