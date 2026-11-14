"""Audit 93: wrapper_no_inputs. Category: wrapper-fixtures."""
from client import *

body = {'fixture': 'wrapper/no_inputs', 'values': {}, 'uploads': {}, 'today': '2026-11-11', 'run_id': 'fixture'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'wrapper', body)
        assert got['main'] == '/* SAShiny 1 wrapper: generated, do not edit */\n%put NOTE: SASHINY-BEGIN run=fixture;\n%let syscc = 0;\n%put NOTE: SASHINY-BEGIN-PROGRAM;\nproc print data=sashelp.class;\nrun;\n%put NOTE: SASHINY-END-PROGRAM;\n%put NOTE: SASHINY-END run=fixture syscc=&syscc;\n', (language, got)
        assert not got['issues']
        assert got['reset'] == '/* SAShiny 1 reset */\nproc datasets library=work kill nolist nowarn;\nquit;\n'
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
