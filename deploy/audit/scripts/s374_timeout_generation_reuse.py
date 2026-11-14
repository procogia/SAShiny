"""Audit 374: timeout_generation_reuse. Category: engine-lifecycle."""
from client import *

got=value('python','generation_cancel',{'data':{'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'report': {'type': 'log'}}, 'run': {'timeout_seconds': 1}}})
assert got['old']['status']=='error' and got['new']['status']=='success',got
assert got['sessions_created']==2 and all(got['closed_before_cleanup']),got
