"""Audit 213: xpt_member_length_8. Category: download-formats."""
from client import *

body = {'function': 'xpt_bytes', 'args': [{'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'AAAAAAAA']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        raw=base64.b64decode(got['base64'])
        assert b'LIBRARY' in raw[:100],raw[:100]
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
