"""Audit 273: connect_unknown_python. Category: connection-configuration."""
from client import *

expect_exception('python','connect',{'kwargs':{'profile':'unknown'}},'unknown profile')
