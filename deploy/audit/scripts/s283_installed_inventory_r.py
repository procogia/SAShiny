"""Audit 283: installed_inventory_r. Category: dependencies."""
from client import *

got=value('r','inventory',{})
assert all(got['backends'].values()),got
assert len(got['versions'])>=10,got
