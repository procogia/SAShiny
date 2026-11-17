"""Platform deployment targets (spec ``CONTRACT.md`` §6.8.x).

Importing this package registers every platform target with
:mod:`sashiny.deploy`.
"""

from __future__ import annotations

from . import aws, azure, snowflake

__all__ = ["aws", "azure", "snowflake"]
