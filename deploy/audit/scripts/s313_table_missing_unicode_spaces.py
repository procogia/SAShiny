"""Audit 313: table_missing_unicode_spaces. Category: table-collection."""
from client import *

body = {'function': 'build_table', 'args': [[{'name': 'Age', 'type': 'numeric', 'label': 'Age label', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}], [[None, ' a \t'], [12, 'b\xa0']]], 'kwargs': {'total_rows': 3, 'max_rows': 2, 'formatted': False}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got['rows']==[[None,' a'],[12,'b\u00a0']],got
        assert got['truncated'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
