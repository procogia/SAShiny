"""Audit 244: pool_shared_engine. Category: pool-concurrency."""
from client import *

got=value('python','pool',{'scenario': 'shared_engine', 'delay': 0.12, 'config': {'max_size': 2, 'acquire_timeout': 2}})
assert all(r['status']=='success' for r in got['results']),got
assert not got['errors'],got
assert got['counts']['peak']<=2,got
