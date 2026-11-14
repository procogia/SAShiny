"""Audit 198: upload_empty_file_r. Category: upload-conversion."""
from client import *

expect_exception('r','upload',{'name': 'input.csv', 'files': [{'name': 'input.csv', 'text': ''}], 'spec': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}})
