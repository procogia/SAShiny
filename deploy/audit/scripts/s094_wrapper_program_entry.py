"""Audit 94: wrapper_program_entry. Category: wrapper-fixtures."""
from client import *

body = {'fixture': 'wrapper/program_entry', 'values': {'min_msrp': 25000, 'origins': ['USA', 'Asia'], 'note': "It's 100% & done"}, 'uploads': {}, 'today': '2026-11-11', 'run_id': 'fixture'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'wrapper', body)
        assert got['main'] == "/* SAShiny 1 wrapper: generated, do not edit */\n%put NOTE: SASHINY-BEGIN run=fixture;\n%let syscc = 0;\ndata _null_;\n  call symputx('MIN_MSRP', '25000', 'G');\n  call symputx('ORIGINS', '''Asia'' ''USA''', 'G');\n  call symputx('N_ORIGINS', '2', 'G');\n  call symputx('NOTE', 'It''s 100% & done', 'G');\nrun;\n%let NOTE = %superq(NOTE);\n%put NOTE: SASHINY-BEGIN-PROGRAM;\ndata work.stats;\n  set sashelp.cars;\nrun;\n%put NOTE: SASHINY-END-PROGRAM;\n%put NOTE: SASHINY-END run=fixture syscc=&syscc;\n", (language, got)
        assert not got['issues']
        assert got['reset'] == '/* SAShiny 1 reset */\nproc datasets library=work kill nolist nowarn;\nquit;\n%symdel MIN_MSRP ORIGINS N_ORIGINS NOTE / nowarn;\n'
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
