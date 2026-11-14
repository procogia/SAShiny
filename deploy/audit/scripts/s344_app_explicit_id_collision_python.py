"""Audit 344: app_explicit_id_collision_python. Category: app."""
from client import *

expect_exception('python','app',{'data':{'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'report': {'type': 'log'}}, 'id': 'same'},'duplicate':True},'duplicate')
