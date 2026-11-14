"""Audit 262: app_duplicate_python. Category: app."""
from client import *

expect_exception('python','app',{'duplicate':True},'duplicate')
