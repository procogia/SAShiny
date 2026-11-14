"""Audit 312: column_selection_error_r. Category: table-collection."""
from client import *

expect_exception('r','collect',{'function':'select_columns','args':[[{'name': 'Age', 'type': 'numeric', 'label': 'Age label', 'format': ''}, {'name': 'NAME', 'type': 'character', 'label': '', 'format': ''}],['absent']]})
