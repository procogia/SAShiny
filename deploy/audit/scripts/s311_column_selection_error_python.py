"""Audit 311: column_selection_error_python. Category: table-collection."""
from client import *

expect_exception('python','collect',{'function':'select_columns','args':[[{'name': 'Age', 'type': 'numeric', 'label': 'Age label', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}],['absent']]})
