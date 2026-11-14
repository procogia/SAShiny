"""Audit 243: pool_timeout. Category: pool-concurrency."""
from client import *

got=value('python','pool',{'scenario': 'timeout', 'delay': 0.12, 'config': {'max_size': 2, 'acquire_timeout': 0.03}})
assert sum(r['status']=='error' for r in got['results'])==2,got
assert not got['errors'],got
assert got['counts']['peak']<=2,got
