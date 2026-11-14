"""Audit 188: upload_bad_date_python. Category: upload-conversion."""
from client import *

expect_exception('python','upload',{'name': 'input.csv', 'files': [{'name': 'input.csv', 'text': 'age,day\n12,not-a-date\n'}], 'spec': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}})
