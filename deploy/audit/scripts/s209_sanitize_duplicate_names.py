"""Audit 209: sanitize_duplicate_names. Category: upload-conversion."""
from client import *

body = {'names': ['1 item', 'x', 'X', 'x', 'x_2', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'sanitize', body)
        assert got==['_1_item', 'x', 'X_2', 'x_3', 'x_2_2', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa_2'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
