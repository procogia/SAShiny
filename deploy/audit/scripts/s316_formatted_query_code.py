"""Audit 316: formatted_query_code. Category: generated-query."""
from client import *

body = {'function': 'formatted_table_code', 'args': ['WORK', 'OUT', ['AGE', 'NAME'], 3]}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert 'obs=3 keep=AGE NAME' in got and '_sx_c2 = strip(vvalue(NAME));' in got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
