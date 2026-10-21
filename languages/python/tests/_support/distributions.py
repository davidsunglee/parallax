"""The workspace's distributions, and the wheelhouse built from them."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from filelock import FileLock

from tests._support.repo import PY_ROOT

# Production distributions first, then the dev-only conformance tooling.
PRODUCTION_PACKAGES: tuple[str, ...] = (
    "parallax-core",
    "parallax-descriptor",
    "parallax-evolution",
    "parallax-snapshot",
    "parallax-postgres",
    "parallax-aws",
)
ALL_PACKAGES: tuple[str, ...] = (*PRODUCTION_PACKAGES, "parallax-conformance")

# Each distribution's top regular package under the shared PEP 420 namespace.
TOP_PACKAGE_DIR: dict[str, str] = {
    "parallax-core": "parallax/core",
    "parallax-descriptor": "parallax/descriptor",
    "parallax-evolution": "parallax/evolution",
    "parallax-snapshot": "parallax/snapshot",
    "parallax-postgres": "parallax/postgres",
    "parallax-aws": "parallax/aws",
    "parallax-conformance": "parallax/conformance",
}

TOP_PACKAGE_NAMES: tuple[str, ...] = (
    "parallax.core",
    "parallax.descriptor",
    "parallax.evolution",
    "parallax.snapshot",
    "parallax.postgres",
    "parallax.aws",
    "parallax.conformance",
)


@dataclass(frozen=True)
class Wheelhouse:
    """A directory of freshly built wheels plus a package-name -> wheel map."""

    directory: Path
    wheels: dict[str, Path]


def _wheels(directory: Path) -> dict[str, Path]:
    wheels: dict[str, Path] = {}
    for package in ALL_PACKAGES:
        dist = package.replace("-", "_")
        matches = sorted(directory.glob(f"{dist}-*.whl"))
        assert matches, f"no wheel built for {package}"
        wheels[package] = matches[-1]
    return wheels


def build_wheelhouse(directory: Path) -> Wheelhouse:
    """Share a fresh invocation's build across workers; publish only complete output."""
    with FileLock(str(directory.with_suffix(".lock"))):
        if not directory.exists():
            with TemporaryDirectory(prefix="wheelhouse-build-", dir=directory.parent) as temporary:
                staging = Path(temporary)
                for package in ALL_PACKAGES:
                    subprocess.run(
                        [
                            "uv",
                            "build",
                            "--package",
                            package,
                            "--wheel",
                            "--python",
                            sys.executable,
                            "--out-dir",
                            str(staging),
                        ],
                        cwd=PY_ROOT,
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                _wheels(staging)
                staging.rename(directory)
    return Wheelhouse(directory=directory, wheels=_wheels(directory))
