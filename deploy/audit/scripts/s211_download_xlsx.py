"""Audit 211: download_xlsx. Category: download-formats."""
from client import *

body = {'function': 'xlsx_bytes', 'args': [{'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'OUT']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        raw=base64.b64decode(got['base64'])
        assert len(raw)>20,got
        assert raw.startswith(b'PK'),raw[:20]
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
