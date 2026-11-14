"""Audit 277: profiles_read_yaml. Category: connection-configuration."""
from client import *

body = {'yaml': 'default: offline\nprofiles:\n  offline:\n    type: mock\n'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'profiles', body)
        assert got['default']=='offline' and got['profiles']['offline']['type']=='mock',got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
