"""Audit 252: recording_precision. Category: recording."""
from client import *

body = {'recording': {'outputs': {'table': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[9007199254740994, 1.2345678901234567, 'precise']], 'total_rows': 4, 'truncated': False, 'formatted': False}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'recording', body)
        assert got['loaded']['outputs']['table']['rows']==[[9007199254740994, 1.2345678901234567, 'precise']],got
        assert json.loads(got['result_raw'])['outputs']['table']['rows']==[[9007199254740994, 1.2345678901234567, 'precise']],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
