"""Audit 221: plots_select_out_of_range. Category: collect-fixtures."""
from client import *

body={'function': 'extract_plots', 'args': ['<html><body><div class="c"><img alt="Graph 1" class="g" src="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" style="height:480px"></div><p>table</p><IMG SRC="data:image/jpeg;base64,/9j/4AAQ" alt=x><svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg><img src="logo.png"></body></html>', 4]}
for language in ('python','r'):
    expect_exception(language,'collect',body)
