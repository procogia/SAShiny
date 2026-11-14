"""Audit 282: installed_inventory_python. Category: dependencies."""
from client import *

got=value('python','inventory',{})
assert all(got['backends'].values()),got
assert len(got['versions'])>=10,got
