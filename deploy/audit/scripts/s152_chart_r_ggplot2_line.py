"""Audit 152: chart_r_ggplot2_line. Category: charts."""
from client import *

got = value('r','chart',{'value': {'columns': [{'name': 'X', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Y', 'type': 'numeric', 'label': '', 'format': ''}, {'name': 'Group', 'type': 'character', 'label': '', 'format': ''}], 'rows': [[1, 3, 'a'], [2, 4, 'a'], [3, 5, 'b'], [4, 8, 'b']], 'total_rows': 4, 'truncated': False, 'formatted': False}, 'spec': {'kind': 'line', 'x': 'x', 'title': 'Synthetic chart', 'xlab': 'Horizontal', 'ylab': 'Vertical', 'y': 'y'}, 'backend': 'ggplot2'})
validate_png(got['png'])
