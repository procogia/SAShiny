"""Package and spec version information (spec ``CONTRACT.md`` §11)."""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SPEC_RELEASE", "Info", "info"]

# The spec release this library implements. CI (spec/tools/check_versions.py)
# fails when it differs from the spec or from the R package.
SPEC_RELEASE = "1.7"


@dataclass(frozen=True)
class Info:
    """Versions reported by :func:`info`."""

    package: str
    version: str
    spec: str
    contract: int

    def __str__(self) -> str:
        """Return the one-line summary, identical to R's ``sas_info()``."""
        return (
            f"{self.package} {self.version} (spec {self.spec}, contract sashiny: {self.contract})"
        )


def info() -> Info:
    """Return the library version, the spec release and the contract version.

    The R package and the Python library are released together with the same
    version, and both report the same spec release.
    """
    from . import __version__  # noqa: PLC0415 - avoid an import cycle

    return Info(package="sashiny", version=__version__, spec=SPEC_RELEASE, contract=1)
