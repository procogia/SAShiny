"""Audit 377: raster_mapping_python_facet. Category: chart-mapping-semantics."""
from client import *

plain=validate_png(value('python','chart',{'value': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'spec': {'kind': 'scatter', 'x': 'X', 'y': 'Y'}, 'backend': 'matplotlib'})['png'])
mapped=validate_png(value('python','chart',{'value': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'spec': {'kind': 'scatter', 'x': 'X', 'y': 'Y', 'facet': 'Group'}, 'backend': 'matplotlib'})['png'])
assert plain.tobytes()!=mapped.tobytes(),'declared mapping changes no rendered pixels'
