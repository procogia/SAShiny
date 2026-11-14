"""Audit 346: app_explicit_id_collision_r. Category: app."""
from client import *

expect_exception('r','app',{'data':{'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'report': {'type': 'log'}}, 'id': 'same'},'duplicate':True},'duplicate')
