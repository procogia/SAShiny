"""Audit 315: table_metadata_code. Category: generated-query."""
from client import *

body = {'function': 'table_meta_code', 'args': ['WORK', 'OUT']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert 'dictionary.columns' in got and 'nlobs' in got and got.endswith('\n'),got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
