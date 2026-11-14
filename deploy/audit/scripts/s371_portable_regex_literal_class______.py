"""Audit 371: portable_regex_literal_class_[(?=]. Category: regex-literals."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'x': {'type': 'text', 'label': 'X', 'pattern': '[(?=]'}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'validate', body)
        assert not got['issues'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
