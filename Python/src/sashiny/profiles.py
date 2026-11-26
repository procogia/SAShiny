"""SAS connection profiles for deployment (spec ``CONTRACT.md`` §6.8).

A profile names the SAS system a deployed app connects to. It is used by
:mod:`sashiny.deploy` to derive egress endpoints, the Java requirement and the
runtime environment variables, and by :func:`connect_from_env` inside a deployed
app to build the engine from those variables.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from .engines.saspy import ODA_HOSTS, SaspyEngine, connect, oda, sas94_iom, sas94_ssh, viya
from .errors import DeployError

__all__ = ["Profile", "connect_from_env", "parse_profile"]

METHODS = ("iom", "http", "ssh")
SECRETS = ("SASHINY_SAS_USER", "SASHINY_SAS_PASSWORD")
_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f\"'\\$`]")
_UNSAFE_PATH = re.compile(r"[\t\n\r\x00-\x1f\x7f\"'\\$`]")
_MAX_PORT = 65535
_DEFAULT_IOM_PORT = 8591
# The workspace range observed during ODA deployment verification (#177).
_ODA_PORTS = (_DEFAULT_IOM_PORT, "8800-8999")


@dataclass(frozen=True)
class Profile:
    """A validated SAS connection profile (spec §6.8)."""

    name: str
    method: str
    oda_region: str | None = None
    iomhost: str | None = None
    iomport: int = _DEFAULT_IOM_PORT
    url: str | None = None
    host: str | None = None
    saspath: str | None = None
    requires_vpn: bool = False

    @property
    def kind(self) -> str:
        """``oda``, ``viya`` or ``sas94``."""
        if self.oda_region:
            return "oda"
        return "viya" if self.method == "http" else "sas94"

    @property
    def needs_java(self) -> bool:
        """Whether the runtime needs Java 17 (every IOM profile)."""
        return self.method == "iom"

    @property
    def endpoints(self) -> list[str]:
        """The hosts and TCP ports or port ranges the deployed app must reach."""
        if self.oda_region:
            return [f"{host}:{port}" for host in ODA_HOSTS[self.oda_region] for port in _ODA_PORTS]
        if self.method == "iom":
            return [f"{self.iomhost}:{self.iomport}"]
        if self.method == "http":
            parts = urlsplit(str(self.url))
            port = parts.port or (443 if parts.scheme == "https" else 80)
            return [f"{parts.hostname}:{port}"]
        return [f"{self.host}:22"]

    @property
    def env(self) -> list[tuple[str, str]]:
        """Plain runtime environment variables, in spec order."""
        out = [("SASHINY_LICENSE_ACK", "true"), ("SASHINY_PROFILE", self.kind)]
        if self.oda_region:
            out.append(("SASHINY_ODA_REGION", self.oda_region))
        elif self.method == "http":
            out.append(("SASHINY_VIYA_URL", str(self.url)))
        elif self.method == "iom":
            out += [
                ("SASHINY_SAS94_HOST", str(self.iomhost)),
                ("SASHINY_SAS94_PORT", str(self.iomport)),
            ]
        else:
            out += [
                ("SASHINY_SAS94_HOST", str(self.host)),
                ("SASHINY_SAS94_SASPATH", str(self.saspath)),
            ]
        return out

    @property
    def secrets(self) -> list[str]:
        """Names of the secret environment variables (values live in the platform)."""
        return [] if self.method == "ssh" else list(SECRETS)


def _fail(name: str, message: str) -> DeployError:
    # DeployError is a ValueError, and matches R's sashiny_error_deploy.
    return DeployError(f"profile {name}: {message}")


def _safe(name: str, field: str, value: Any, *, path: bool = False) -> str:
    if not isinstance(value, str) or not value:
        raise _fail(name, f"{field} must be a non-empty string")
    if (_UNSAFE_PATH if path else _UNSAFE).search(value):
        raise _fail(name, f"{field} contains characters that are not allowed")
    return value


def parse_profile(data: dict[str, Any], name: str | None = None) -> Profile:
    """Validate a profile mapping (spec §6.8) and return a :class:`Profile`.

    Args:
        data: The profile fields, for example one entry of a connections file.
        name: The profile name; defaults to ``data["name"]``.

    Returns:
        The validated profile.

    Raises:
        ValueError: With a message starting ``profile <name>: `` when invalid.

    """
    pname = str(name or data.get("name") or "profile")
    method = data.get("method")
    if method not in METHODS:
        raise _fail(pname, "method must be one of iom, http or ssh")
    vpn = data.get("requires_vpn", False)
    if not isinstance(vpn, bool):
        raise _fail(pname, "requires_vpn must be true or false")
    region = data.get("oda_region")
    if region is not None:
        if method != "iom":
            raise _fail(pname, "oda_region needs method iom")
        if region not in ODA_HOSTS:
            raise _fail(pname, f"unknown oda_region; expected one of {', '.join(ODA_HOSTS)}")
        return Profile(pname, method, oda_region=str(region), requires_vpn=vpn)
    if method == "iom":
        if not data.get("iomhost"):
            raise _fail(pname, "an iom profile needs oda_region or iomhost")
        host = _safe(pname, "iomhost", data["iomhost"])
        port = data.get("iomport", _DEFAULT_IOM_PORT)
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= _MAX_PORT:
            raise _fail(pname, "iomport must be an integer from 1 to 65535")
        return Profile(pname, method, iomhost=host, iomport=port, requires_vpn=vpn)
    if method == "http":
        url = data.get("url")
        if not isinstance(url, str) or not re.match(r"^https?://", url):
            raise _fail(pname, "an http profile needs a url starting with https:// or http://")
        _safe(pname, "url", url)
        if not urlsplit(url).hostname:
            raise _fail(pname, "url has no host")
        return Profile(pname, method, url=url, requires_vpn=vpn)
    if not data.get("host") or not data.get("saspath"):
        raise _fail(pname, "an ssh profile needs host and saspath")
    host = _safe(pname, "host", data["host"])
    saspath = _safe(pname, "saspath", data["saspath"], path=True)
    return Profile(pname, method, host=host, saspath=saspath, requires_vpn=vpn)


def connect_from_env(*, license_ack: bool | None = None) -> SaspyEngine:
    """Build the engine of a deployed app from its environment (spec §6.8).

    Reads ``SASHINY_PROFILE`` (``oda``, ``viya`` or ``sas94``) and the
    connection variables a deployment target sets, then calls
    :func:`sashiny.connect`. The licence is acknowledged by
    ``SASHINY_LICENSE_ACK`` unless ``license_ack`` is given.

    Raises:
        ValueError: If ``SASHINY_PROFILE`` or a required variable is missing.

    """
    env = os.environ
    kind = env.get("SASHINY_PROFILE", "")
    if kind == "oda":
        return connect(oda(env.get("SASHINY_ODA_REGION") or "us1"), license_ack=license_ack)
    if kind == "viya":
        url = env.get("SASHINY_VIYA_URL")
        if not url:
            raise DeployError("SASHINY_VIYA_URL is required when SASHINY_PROFILE=viya")
        return connect(viya(url), license_ack=license_ack)
    if kind == "sas94":
        host = env.get("SASHINY_SAS94_HOST")
        if not host:
            raise DeployError("SASHINY_SAS94_HOST is required when SASHINY_PROFILE=sas94")
        saspath = env.get("SASHINY_SAS94_SASPATH") or None
        port = int(env.get("SASHINY_SAS94_PORT") or _DEFAULT_IOM_PORT)
        backend = sas94_ssh(host, saspath) if saspath else sas94_iom(host, port=port)
        return connect(backend, license_ack=license_ack)
    raise DeployError("SASHINY_PROFILE must be oda, viya or sas94")
