"""Audit 361: xlsx_cells_r_native_dates_and_blank. Category: xlsx-native-cells."""
from client import *

binary=value('python','make_upload',{'columns':['age','day'],'rows':[[12, {'date': '2026-01-01'}], [13, None]]})['base64']
request={'name':'data.xlsx','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'age', 'type': 'numeric'}, {'name': 'day', 'type': 'date'}]},'files':[{'name':'data.xlsx','base64':binary}]}
got=value('r','upload',request)
assert len(got['rows'])==2,got
