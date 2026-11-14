"""Audit 224: recording_key_text. Category: recording-keys."""
from client import *

body = {'function': 'recording_key_text', 'args': ['3f1c0000000000000000000000000000000000000000000000000000000000aa', [['MIN_MSRP', '25000'], ['ORIGINS', "'Asia' 'USA'"], ['N_ORIGINS', '2'], ['NOTE', "It's 100% & done"]], [['adsl', '9b2d0000000000000000000000000000000000000000000000000000000000bb']]]}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got=="sashiny-recording-key 1\ncontract 3f1c0000000000000000000000000000000000000000000000000000000000aa\nmacro MIN_MSRP=25000\nmacro ORIGINS='Asia' 'USA'\nmacro N_ORIGINS=2\nmacro NOTE=It's 100% & done\nupload adsl 9b2d0000000000000000000000000000000000000000000000000000000000bb\n",got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
