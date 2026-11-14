"""Audit 368: native_sas7bdat_upload_python. Category: native-sas7bdat."""
from client import *

binary=value('r','make_upload',{'columns':['AGE','NAME'],'rows':[[12,'Ann'],[13,'Ben']]})['base64']
got=value('python','upload',{'name':'data.sas7bdat','spec':{'type': 'dataset', 'target': 'work.data', 'columns': [{'name': 'AGE', 'type': 'numeric'}, {'name': 'NAME', 'type': 'character'}]},'files':[{'name':'data.sas7bdat','base64':binary}]})
assert got['rows']==[[12,'Ann'],[13,'Ben']],got
