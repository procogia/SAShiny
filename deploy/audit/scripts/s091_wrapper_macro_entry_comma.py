"""Audit 91: wrapper_macro_entry_comma. Category: wrapper-fixtures."""
from client import *

body = {'fixture': 'wrapper/macro_entry_comma', 'values': {'arms': ['Placebo', 'Drug A']}, 'uploads': {}, 'today': '2026-11-11', 'run_id': 'fixture'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'wrapper', body)
        assert got['main'] == "/* SAShiny 1 wrapper: generated, do not edit */\n%put NOTE: SASHINY-BEGIN run=fixture;\n%let syscc = 0;\ndata _null_;\n  call symputx('ARMS', '''Placebo'', ''Drug A''', 'G');\nrun;\n%put NOTE: SASHINY-BEGIN-PROGRAM;\n%macro arms_table(arms=);\n  %put NOTE: &arms;\n%mend arms_table;\n%arms_table(ARMS=%bquote(&ARMS));\n%put NOTE: SASHINY-END-PROGRAM;\n%put NOTE: SASHINY-END run=fixture syscc=&syscc;\n", (language, got)
        assert not got['issues']
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
