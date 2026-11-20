"""SAShiny: use unchanged SAS programs as the server of Shiny applications.

SAS is a registered trademark of SAS Institute Inc. Shiny is a registered
trademark of Posit Software, PBC. This project is not affiliated with or
endorsed by either company.
"""

from typing import Any

from .charts import chart_backends, render_chart
from .contract import Contract, Issue, default_module_id, load, validate
from .engines import (
    Backend,
    Engine,
    ProcPythonEngine,
    SaspyEngine,
    connect,
    connect_in_session,
    load_profiles,
    oda,
    sas94_iom,
    sas94_ssh,
    viya,
)
from .errors import (
    ContractError,
    DeployError,
    EngineError,
    LicenseError,
    RunError,
    SashinyError,
    ValuesError,
)
from .lint import lint
from .pool import Pool
from .profiles import Profile, connect_from_env, parse_profile
from .publish import publish
from .result import LogLine, Result, TableResult
from .run import close, run
from .upload import UploadError, UploadFile
from .values import json_values, render_values
from .wrapper import reset_code, wrapper_code

__all__ = [
    "Backend",
    "Contract",
    "ContractError",
    "DeployError",
    "Engine",
    "EngineError",
    "Issue",
    "LicenseError",
    "LogLine",
    "Pool",
    "ProcPythonEngine",
    "Profile",
    "Result",
    "RunError",
    "SashinyError",
    "SaspyEngine",
    "TableResult",
    "UploadError",
    "UploadFile",
    "ValuesError",
    "__version__",
    "app",
    "chart_backends",
    "close",
    "connect",
    "connect_from_env",
    "connect_in_session",
    "default_module_id",
    "deploy",
    "json_values",
    "lint",
    "load",
    "load_profiles",
    "oda",
    "parse_profile",
    "publish",
    "render_chart",
    "render_values",
    "reset_code",
    "run",
    "sas94_iom",
    "sas94_ssh",
    "validate",
    "viya",
    "wrapper_code",
]

__version__ = "0.3.0"


def __getattr__(name: str) -> Any:
    """Lazily expose ``app`` and ``modules``, which need the optional ``shiny``.

    The core package must import without ``shiny`` installed (it is an optional
    extra). ``app`` and ``modules`` are only imported when first accessed.
    """
    if name == "app":
        from .app import app as _app  # noqa: PLC0415 - optional dependency

        globals()["app"] = _app
        return _app
    if name == "deploy":
        from importlib import import_module  # noqa: PLC0415 - keep import time low

        _deploy = import_module(f"{__name__}.deploy")
        globals()["deploy"] = _deploy
        return _deploy
    if name == "modules":
        from importlib import import_module  # noqa: PLC0415 - optional dependency

        _modules = import_module(f"{__name__}.modules")
        globals()["modules"] = _modules
        return _modules
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
