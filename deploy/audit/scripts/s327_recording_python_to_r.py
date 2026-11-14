"""Audit 327: recording_python_to_r. Category: recording-interoperability."""
from client import *

written=value('python','recording',{'recording':{'status': 'success', 'log': 'NOTE: Unicode λ', 'outputs': {'t': {'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}}}})
got=value('r','raw_replay',{'raw':written['raw']})
assert got['outputs']=={'t': {'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}},got
assert got['metadata']['recording']=='replayed',got
