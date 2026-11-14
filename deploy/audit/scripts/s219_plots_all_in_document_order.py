"""Audit 219: plots_all_in_document_order. Category: collect-fixtures."""
from client import *

body={'function': 'extract_plots', 'args': ['<html><body><div class="c"><img alt="Graph 1" class="g" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" style="height:480px"></div><p>table</p><IMG SRC="data:image/jpeg;base64,/9j/4AAQ" alt=x><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg><img src="logo.png"></body></html>', None]}
for language in ('python','r'):
    assert value(language,'collect',body)==[{'mime': 'image/png', 'data': 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=='}, {'mime': 'image/jpeg', 'data': '/9j/4AAQ'}, {'mime': 'image/svg+xml', 'data': 'PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIxMCIgaGVpZ2h0PSIxMCI+PHJlY3Qgd2lkdGg9IjEwIiBoZWlnaHQ9IjEwIi8+PC9zdmc+'}]
