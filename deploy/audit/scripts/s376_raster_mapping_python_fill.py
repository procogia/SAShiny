"""Audit 376: raster_mapping_python_fill. Category: chart-mapping-semantics."""
from client import *

plain=validate_png(value('python','chart',{'value': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'spec': {'kind': 'bar', 'x': 'X', 'y': 'Y'}, 'backend': 'matplotlib'})['png'])
mapped=validate_png(value('python','chart',{'value': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'spec': {'kind': 'bar', 'x': 'X', 'y': 'Y', 'fill': 'Group'}, 'backend': 'matplotlib'})['png'])
assert plain.tobytes()!=mapped.tobytes(),'declared mapping changes no rendered pixels'
