"""Audit 207: upload_quoted_cells_r. Category: upload-conversion."""
from client import *

got=value('r','upload',{'name': 'input.csv', 'files': [{'name': 'input.csv', 'text': 'age,day\n"12","2026-01-01"\n'}], 'spec': {'type': 'dataset', 'label': 'Data', 'target': 'work.data', 'accept': ['csv', 'xlsx', 'xpt', 'sas7bdat'], 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]}})
assert got['columns']==['age','day'],got
