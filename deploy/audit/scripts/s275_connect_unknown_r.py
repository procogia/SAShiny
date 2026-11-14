"""Audit 275: connect_unknown_r. Category: connection-configuration."""
from client import *

expect_exception('r','connect',{'kwargs':{'profile':'unknown'}},'unknown profile')
