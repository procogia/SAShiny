"""Audit 317: dynamic_choices_query. Category: generated-query."""
from client import *

body = {'function': 'choices_code', 'args': [{'dataset': 'WORK.CHOICES', 'value_column': 'CODE', 'label_column': 'LABEL', 'max_choices': 7}]}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert 'outobs=7' in got and 'where not missing(CODE)' in got and 'order by CODE' in got,got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
