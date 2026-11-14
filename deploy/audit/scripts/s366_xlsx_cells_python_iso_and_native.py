"""Audit 366: xlsx_cells_python_iso_and_native. Category: xlsx-native-cells."""
from client import *

binary=value('python','make_upload',{'columns':['age','day'],'rows':[[12, '2026-01-01'], [13, {'date': '2026-01-02'}]]})['base64']
request={'name':'data.xlsx','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]},'files':[{'name':'data.xlsx','base64':binary}]}
got=value('python','upload',request)
assert len(got['rows'])==2,got
