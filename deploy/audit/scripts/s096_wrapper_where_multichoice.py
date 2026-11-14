"""Audit 96: wrapper_where_multichoice. Category: wrapper-fixtures."""
from client import *

body = {'fixture': 'wrapper/where_multichoice', 'values': {'min_msrp': 25000, 'origins': ['Asia', 'Europe', 'USA']}, 'uploads': {}, 'today': '2026-11-11', 'run_id': 'fixture'}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'wrapper', body)
        assert got['main'] == "/* SAShiny 1 wrapper: generated, do not edit */\n%put NOTE: SASHINY-BEGIN run=fixture;\n%let syscc = 0;\ndata _null_;\n  call symputx('MIN_MSRP', '25000', 'G');\n  call symputx('ORIGINS', '''Asia'' ''Europe'' ''USA''', 'G');\n  call symputx('N_ORIGINS', '3', 'G');\nrun;\n%put NOTE: SASHINY-BEGIN-PROGRAM;\ndata work.t;\n  set sashelp.cars;\n  where origin in (&ORIGINS) and msrp >= &MIN_MSRP;\nrun;\n%put NOTE: SASHINY-END-PROGRAM;\n%put NOTE: SASHINY-END run=fixture syscc=&syscc;\n", (language, got)
        assert not got['issues']
        assert got['reset'] == '/* SAShiny 1 reset */\nproc datasets library=work kill nolist nowarn;\nquit;\n%symdel MIN_MSRP ORIGINS N_ORIGINS / nowarn;\n'
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
