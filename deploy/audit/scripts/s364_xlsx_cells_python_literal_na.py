"""Audit 364: xlsx_cells_python_literal_NA. Category: xlsx-native-cells."""
from client import *

binary=value('python','make_upload',{'columns':['age','day'],'rows':[[12, 'NA'], [13, {'date': '2026-01-01'}]]})['base64']
request={'name':'data.xlsx','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]},'files':[{'name':'data.xlsx','base64':binary}]}
expect_exception('python','upload',request)
