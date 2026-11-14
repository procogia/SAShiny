"""Audit 328: recording_r_to_python. Category: recording-interoperability."""
from client import *

written=value('r','recording',{'recording':{'status': 'success', 'log': 'NOTE: Unicode λ', 'outputs': {'t': {'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}}}})
got=value('python','raw_replay',{'raw':written['raw']})
assert got['outputs']=={'t': {'columns': [{'name': 'AGE', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[12, 'Ann'], [None, 'Ben']], 'total_rows': 2, 'truncated': False, 'formatted': False}},got
assert got['metadata']['recording']=='replayed',got
