"""Audit 200: upload_header_only_python. Category: upload-conversion."""
from client import *

got=value('python','upload',{'name': 'input.csv', 'files': [{'name': 'input.csv', 'text': 'age,day\n'}], 'spec': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}})
assert got['columns']==['age','day'],got
