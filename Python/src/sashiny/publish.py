"""Publishing SAShiny apps to Posit Connect (spec ``CONTRACT.md`` §6.7).

:func:`publish` deploys an app directory with the official ``rsconnect-python``
client (the ``sashiny[connect]`` extra). Credential files are never bundled. SAS
credentials and the licence acknowledgement reach the deployed app only as
Connect environment variables. ``rsconnect`` reads their values from this
process and sends them over an encrypted connection, and they are not stored in
the bundle.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Literal

__all__ = ["PublishResult", "bundle_files", "on_connect", "publish"]

SECRET_NAMES = frozenset({".authinfo", "_authinfo", ".netrc", "_netrc", ".Renviron", ".env"})
SECRET_SUFFIXES = (".pem", ".key")
_SKIP_DIRS = frozenset(
    {".git", ".venv", "__pycache__", "rsconnect", "rsconnect-python", ".Rproj.user"}
)


@dataclass
class PublishResult:
    """What :func:`publish` deployed."""

    files: list[str]
    excluded: list[str]
    env_vars: list[str]
    command: list[str] = field(default_factory=list)


def _is_secret(name: str) -> bool:
    return name in SECRET_NAMES or name.lower().endswith(SECRET_SUFFIXES)


def bundle_files(app_dir: str | Path) -> tuple[list[str], list[str]]:
    """Split an app directory into files to bundle and credential files left out.

    Files under a skipped directory (``.git``, ``.venv``, ``__pycache__``,
    ``rsconnect``, ``rsconnect-python``, ``.Rproj.user``) at any depth are
    neither bundled nor reported (spec §6.8).

    Returns:
        ``(files, excluded)``, POSIX paths relative to ``app_dir``, sorted by
        their UTF-8 bytes.

    """
    root = Path(app_dir)
    files: list[str] = []
    excluded: list[str] = []
    for path in root.rglob("*"):
        rel = PurePosixPath(path.relative_to(root).as_posix())
        if not path.is_file() or any(part in _SKIP_DIRS for part in rel.parts):
            continue
        (excluded if _is_secret(rel.name) else files).append(str(rel))
    key = lambda p: p.encode("utf-8")  # noqa: E731 - spec §6.8 byte order
    return sorted(files, key=key), sorted(excluded, key=key)


def on_connect() -> bool:
    """Whether this process runs on Posit Connect."""
    env = os.environ
    return (
        env.get("RSTUDIO_PRODUCT", "").upper() == "CONNECT"
        or bool(env.get("CONNECT_SERVER_URL"))
        or bool(env.get("CONNECT_CONTENT_GUID"))
    )


def _run_rsconnect(args: Sequence[str], env: dict[str, str]) -> None:
    exe = shutil.which("rsconnect")
    command = [exe] if exe else [sys.executable, "-m", "rsconnect.main"]
    subprocess.run([*command, *args], env=env, check=True)  # noqa: S603


def publish(  # noqa: PLR0913 - explicit deployment options
    app_dir: str | Path,
    *,
    title: str | None = None,
    name: str | None = None,
    sas_credentials: Literal["env", "server"] = "env",
    license_ack: bool = False,
    env_vars: Sequence[str] = (),
    runner: Callable[[Sequence[str], dict[str, str]], None] | None = None,
) -> PublishResult:
    """Publish a SAShiny app to Posit Connect.

    **Authentication.** Either a server registered with ``rsconnect add`` (pass
    its nickname as ``name``), or the environment variables ``CONNECT_SERVER``
    and ``CONNECT_API_KEY``, which ``rsconnect`` reads directly. The API key is
    never passed on the command line or written to the bundle.

    **SAS credentials.** Credential files (``.authinfo``, ``.Renviron``,
    ``.env``, ``*.pem``, ``*.key``) are never bundled. With
    ``sas_credentials="env"`` the values of ``SASHINY_SAS_USER`` and
    ``SASHINY_SAS_PASSWORD`` in this process are sent to Connect as content
    environment variables. With ``"server"`` the app relies on an
    administrator-managed ``~/.authinfo``.

    **Licence.** ``license_ack=True`` is required. It confirms that the deployed
    app runs programs only on a SAS system you are licensed to use and sets
    ``SASHINY_LICENSE_ACK=true`` on the content.

    Args:
        app_dir: The app directory; it must contain ``app.py``.
        title: The content title.
        name: The nickname of a server registered with ``rsconnect add``.
        sas_credentials: ``"env"`` or ``"server"`` (see above).
        license_ack: Must be ``True``.
        env_vars: Names of further environment variables to send.
        runner: Testing hook replacing the ``rsconnect`` CLI call.

    Returns:
        The bundled files, the excluded credential files and the variable names sent.

    Raises:
        ValueError: Missing licence acknowledgement, app file or SAS credentials.

    """
    if not license_ack:
        raise ValueError(
            "publishing requires license_ack=True: confirm that the deployed app runs "
            "programs only on a SAS system you are licensed to use"
        )
    root = Path(app_dir).resolve()
    if not (root / "app.py").is_file():
        raise ValueError(f"app_dir must contain app.py: {root}")
    names = ["SASHINY_LICENSE_ACK", *env_vars]
    if sas_credentials == "env":
        missing = [v for v in ("SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD") if not os.environ.get(v)]
        if missing:
            raise ValueError(
                f"sas_credentials='env' needs {' and '.join(missing)} set in this process; "
                "or use sas_credentials='server'"
            )
        names += ["SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD"]
    names = list(dict.fromkeys(names))
    files, excluded = bundle_files(root)

    env = dict(os.environ)
    env["SASHINY_LICENSE_ACK"] = "true"
    with tempfile.TemporaryDirectory(prefix="sashiny-bundle-") as tmp:
        staged = Path(tmp) / root.name
        for rel in files:
            target = staged / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, target)
        args = ["deploy", "shiny", str(staged)]
        if name:
            args += ["--name", name]
        if title:
            args += ["--title", title]
        for var in names:
            args += ["--environment", var]  # name only: the value is read from env
        (runner or _run_rsconnect)(args, env)
    return PublishResult(files=files, excluded=excluded, env_vars=names, command=args)
