"""Audit 225: recording_key. Category: recording-keys."""
from client import *

body = {'function': 'recording_key', 'args': ['3f1c0000000000000000000000000000000000000000000000000000000000aa', [['MIN_MSRP', '25000'], ['ORIGINS', "'Asia' 'USA'"], ['N_ORIGINS', '2'], ['NOTE', "It's 100% & done"]], [['adsl', '9b2d0000000000000000000000000000000000000000000000000000000000bb']]]}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got=='5e3d8da5a31037c3bfc0fe9664e0f55db08b515255b3ce58d778a973f8dba784',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
