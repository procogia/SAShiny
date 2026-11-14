"""Audit 323: xlsx_interop_python_to_r. Category: format-interoperability."""
from client import *

encoded=value('python','collect',{'function':'xlsx_bytes','args':[{'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}, 'DATA']})['base64']
got=value('r','upload',{'name':'data.xlsx','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'AGE', 'type': 'numeric'}, {'name': 'NAME', 'type': 'character'}]},'files':[{'name':'data.xlsx','base64':encoded}]})
assert got['rows']==[[12,'Ann'],[None,'Ben']],got
