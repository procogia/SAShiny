"""Audit 264: module_id_rules. Category: app."""
from client import *

body = {'names': ['Cars Explorer.sas', '2nd-report.sas', 'Report.SAS', 'dir/report.sas', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.sas']}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'module_id', body)
        assert got==['cars_explorer', 'p_2nd_report', 'report', 'report', 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'],got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
