"""Audit 216: log_program_scope_crlf_and_missing_end. Category: collect-fixtures."""
from client import *

body = {'function': 'scope_log', 'args': ['NOTE: SASHINY-BEGIN-PROGRAM\r\nline a\r\nERROR 22-322: Syntax error.\r\n', 'program']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got==[{'level': 'text', 'text': 'line a'}, {'level': 'error', 'text': 'ERROR 22-322: Syntax error.'}],(language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
