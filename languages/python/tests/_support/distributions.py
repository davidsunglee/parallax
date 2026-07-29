"""The workspace's distributions, and the wheelhouse built from them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Production distributions first, then the dev-only conformance tooling.
PRODUCTION_PACKAGES: tuple[str, ...] = (
    "parallax-core",
    "parallax-descriptor",
    "parallax-snapshot",
    "parallax-postgres",
)
ALL_PACKAGES: tuple[str, ...] = (*PRODUCTION_PACKAGES, "parallax-conformance")

# Each distribution's top regular package under the shared PEP 420 namespace.
TOP_PACKAGE_DIR: dict[str, str] = {
    "parallax-core": "parallax/core",
    "parallax-descriptor": "parallax/descriptor",
    "parallax-snapshot": "parallax/snapshot",
    "parallax-postgres": "parallax/postgres",
    "parallax-conformance": "parallax/conformance",
}

TOP_PACKAGE_NAMES: tuple[str, ...] = (
    "parallax.core",
    "parallax.descriptor",
    "parallax.snapshot",
    "parallax.postgres",
    "parallax.conformance",
)


@dataclass(frozen=True)
class Wheelhouse:
    """A directory of freshly built wheels plus a package-name -> wheel map."""

    directory: Path
    wheels: dict[str, Path]
