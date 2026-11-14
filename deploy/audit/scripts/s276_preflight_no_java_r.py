"""Audit 276: preflight_no_java_r. Category: connection-configuration."""
from client import *

expect_exception('r','preflight',{'config':{'iomhost':'synthetic.invalid'}},'java')
