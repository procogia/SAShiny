"""Audit 329: remote_download_protocols. Category: engine-orchestration."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {}, 'outputs': {'sas7bdat': {'type': 'download', 'format': 'sas7bdat', 'from': 'work.out'}, 'rtf': {'type': 'download', 'format': 'rtf'}, 'pdf': {'type': 'download', 'format': 'pdf'}}}, 'remote_files': {'/sas/work/out.sas7bdat': 'c3ludGhldGljIG5hdGl2ZSBTQVMgZmlsZSB0cmFuc3BvcnQ=', '/sas/work/sashiny_rtf.rtf': 'e1xydGYxIFN5bnRoZXRpYyByZXBvcnR9', '/sas/work/sashiny_pdf.pdf': 'JVBERi0xLjQgc3ludGhldGljIHRyYW5zcG9ydCBvbmx5'}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'fake', body)
        r=got['results'][0]
        assert r['status']=='success',r
        assert not r['metadata']['collect_errors'],r
        assert all('data' in r['outputs'][f] for f in ('sas7bdat','rtf','pdf')),r
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
