"""Audit 215: log_program_scope. Category: collect-fixtures."""
from client import *

body = {'function': 'scope_log', 'args': ['1          /* SAShiny 1 wrapper: generated, do not edit */\n2          %put NOTE: SASHINY-BEGIN run=fixture;\nNOTE: SASHINY-BEGIN run=fixture\n3          %put NOTE: SASHINY-BEGIN-PROGRAM;\nNOTE: SASHINY-BEGIN-PROGRAM\n4          data work.stats;\n5            set sashelp.cars;   \n6          run;\n\nNOTE: There were 428 observations read from the data set SASHELP.CARS.\nWARNING: Variable X is uninitialized.\nERROR: File WORK.NOPE.DATA does not exist.\n7          %put NOTE: SASHINY-END-PROGRAM;\nNOTE: SASHINY-END-PROGRAM\n8          %put NOTE: SASHINY-END run=fixture syscc=8;\nNOTE: SASHINY-END run=fixture syscc=8', 'program']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'collect', body)
        assert got==[{'level': 'text', 'text': '4          data work.stats;'}, {'level': 'text', 'text': '5            set sashelp.cars;'}, {'level': 'text', 'text': '6          run;'}, {'level': 'text', 'text': ''}, {'level': 'note', 'text': 'NOTE: There were 428 observations read from the data set SASHELP.CARS.'}, {'level': 'warning', 'text': 'WARNING: Variable X is uninitialized.'}, {'level': 'error', 'text': 'ERROR: File WORK.NOPE.DATA does not exist.'}, {'level': 'text', 'text': '7          %put NOTE: SASHINY-END-PROGRAM;'}],(language,got)
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
