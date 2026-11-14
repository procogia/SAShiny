"""Audit 245: fake_sas_full_pipeline. Category: engine-orchestration."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'stats': {'type': 'table', 'from': 'work.stats', 'columns': ['AGE', 'name'], 'max_rows': 2}, 'chart': {'type': 'chart', 'from': 'work.stats', 'spec': {'kind': 'scatter', 'x': 'age', 'y': 'age'}}, 'missing': {'type': 'table', 'from': 'work.nope'}, 'report': {'type': 'html'}, 'graphs': {'type': 'plot'}, 'log': {'type': 'log'}, 'csv': {'type': 'download', 'format': 'csv', 'from': 'work.stats'}, 'xlsx': {'type': 'download', 'format': 'xlsx', 'from': 'work.stats'}, 'xpt': {'type': 'download', 'format': 'xpt', 'from': 'work.stats'}}}, 'datasets': {'WORK.STATS': {'columns': ['age', 'name'], 'rows': [[12, 'Ann'], [13, 'Ben'], [14, 'Chen']]}}, 'record': True}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'fake', body)
        r=got['results'][0]
        assert r['status']=='success',got
        assert r['outputs']['stats']['rows']==[[12,'Ann'],[13,'Ben']],r
        assert r['outputs']['stats']['truncated'] is True,r
        assert 'error' in r['outputs']['missing'],r
        assert len(r['metadata']['collect_errors'])==1,r
        assert all(got['closed_after']),got
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
