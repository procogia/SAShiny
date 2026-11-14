"""Audit 274: preflight_no_java_python. Category: connection-configuration."""
from client import *

expect_exception('python','preflight',{'config':{'iomhost':'synthetic.invalid'}},'java')
