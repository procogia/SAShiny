"""Audit 319: dynamic_choices_after_session_failure. Category: dynamic-choices."""
from client import *

got=value('python','choices_cache',{'data':{'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'pick': {'type': 'choice', 'label': 'Pick', 'choices_from': {'dataset': 'work.choices', 'value_column': 'value'}}}, 'outputs': {'report': {'type': 'log'}}}})
assert got['second']['pick'][0]['value']=='new',got
