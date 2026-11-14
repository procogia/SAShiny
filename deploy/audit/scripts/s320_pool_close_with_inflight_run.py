"""Audit 320: pool_close_with_inflight_run. Category: pool-concurrency."""
from client import *

got=value('python','pool',{'scenario':'close_inflight','delay':0.1,'config':{'min_size':1,'max_size':1,'acquire_timeout':1}})
assert got['sessions_before_close']==0,got
