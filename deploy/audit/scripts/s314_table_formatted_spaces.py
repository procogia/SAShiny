"""Audit 314: table_formatted_spaces. Category: table-collection."""
from client import *

body = {'function': 'build_table', 'args': [[{'name': 'Age', 'type': 'numeric', 'label': 'Age label', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], [['  12 ', ' a \t']]], 'kwargs': {'total_rows': None, 'max_rows': 2, 'formatted': True}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got['rows']==[['12','a']],got
        assert got['total_rows'] is None,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
