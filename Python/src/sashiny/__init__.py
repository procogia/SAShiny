"""SAShiny: use unchanged SAS programs as the server of Shiny applications.

SAS is a registered trademark of SAS Institute Inc. Shiny is a registered
trademark of Posit Software, PBC. This project is not affiliated with or
endorsed by either company.
"""

from typing import Any

from .charts import chart_backends, render_chart
from .contract import Contract, Issue, load, validate
from .engines import Engine, MockEngine, SaspyEngine, connect, load_profiles
from .lint import lint
from .pool import Pool
from .recording import load_recording, save_recording
from .result import LogLine, Result, TableResult
from .run import run
from .upload import UploadError, UploadFile
from .values import render_values
from .wrapper import reset_code, wrapper_code

__all__ = [
    "Contract",
    "Engine",
    "Issue",
    "LogLine",
    "MockEngine",
    "Pool",
    "Result",
    "SaspyEngine",
    "TableResult",
    "UploadError",
    "UploadFile",
    "__version__",
    "app",
    "chart_backends",
    "connect",
    "lint",
    "load",
    "load_profiles",
    "load_recording",
    "render_chart",
    "render_values",
    "reset_code",
    "run",
    "save_recording",
    "validate",
    "wrapper_code",
]

__version__ = "0.1.6"


def __getattr__(name: str) -> Any:
    """Lazily expose ``app`` and ``modules``, which need the optional ``shiny``.

    The core package must import without ``shiny`` installed (it is an optional
    extra). ``app`` and ``modules`` are only imported when first accessed.
    """
    if name == "app":
        from .app import app as _app  # noqa: PLC0415 - optional dependency

        globals()["app"] = _app
        return _app
    if name == "modules":
        from importlib import import_module  # noqa: PLC0415 - optional dependency

        _modules = import_module(f"{__name__}.modules")
        globals()["modules"] = _modules
        return _modules
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
