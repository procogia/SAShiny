"""Audit 322: csv_interop_r_to_python. Category: format-interoperability."""
from client import *

encoded=value('r','collect',{'function':'csv_bytes','args':[{'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}]})['base64']
got=value('python','upload',{'name':'data.csv','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'AGE', 'type': 'numeric'}, {'name': 'NAME', 'type': 'character'}]},'files':[{'name':'data.csv','base64':encoded}]})
assert got['rows']==[[12,'Ann'],[None,'Ben']],got
