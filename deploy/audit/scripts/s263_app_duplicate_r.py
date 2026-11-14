"""Audit 263: app_duplicate_r. Category: app."""
from client import *

expect_exception('r','app',{'duplicate':True},'duplicate')
