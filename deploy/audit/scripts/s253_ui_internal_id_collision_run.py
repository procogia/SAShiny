"""Audit 253: ui_internal_id_collision_run. Category: ui-identifiers."""
from client import *

body = {'data': {'sashiny': 1, 'program': 'program.sas', 'title': 'Audit', 'inputs': {'run': {'type': 'text', 'label': 'Collision', 'optional': True}}, 'outputs': {'report': {'type': 'log'}}}}
failures = []
for language in ('python', 'r'):
    try:
        got = value(language, 'ui', body)
        from html.parser import HTMLParser
        class IDs(HTMLParser):
            def __init__(self):
                super().__init__(); self.ids=[]
            def handle_starttag(self,tag,attrs):
                self.ids.extend(v for k,v in attrs if k=='id')
        parser=IDs(); parser.feed(got['html'])
        assert len(parser.ids)==len(set(parser.ids)),parser.ids
    except AssertionError as exc:
        failures.append((language, str(exc)))
assert not failures, failures
