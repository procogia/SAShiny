"""Audit 186: upload_bad_number_r. Category: upload-conversion."""
from client import *

expect_exception('r','upload',{'name': 'input.csv', 'files': [{'name': 'input.csv', 'text': 'age,day\nnot-a-number,2026-01-01\n'}], 'spec': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}})
