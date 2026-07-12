"""Clean-install production topology proofs (§8 / §10 `clean_install` marker).

Each of the three §8 selective topologies is installed into a fresh uv venv
from the locally built wheels, and the installed distribution list + import
space are probed to prove that unselected lifecycles, the driver, and the
dev-only conformance tooling are all absent.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import Wheelhouse

pytestmark = pytest.mark.clean_install


def _make_venv(root: Path) -> Path:
    subprocess.run(["uv", "venv", str(root)], check=True, capture_output=True, text=True)
    python = root / "bin" / "python"
    assert python.exists(), python
    return python


def _install(python: Path, wheelhouse: Wheelhouse, *packages: str) -> None:
    subprocess.run(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(python),
            "--find-links",
            str(wheelhouse.directory),
            *packages,
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def _import_ok(python: Path, module: str) -> bool:
    result = subprocess.run([str(python), "-c", f"import {module}"], capture_output=True, text=True)
    return result.returncode == 0


def _dist_installed(python: Path, distribution: str) -> bool:
    result = subprocess.run(
        [str(python), "-c", f"import importlib.metadata as m; m.distribution('{distribution}')"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_core_alone(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-core")

    assert _import_ok(python, "parallax.core")
    # Unselected lifecycle, adapter, driver, and dev tooling are all absent.
    assert not _import_ok(python, "parallax.snapshot")
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "psycopg")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")


def test_core_and_snapshot(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-snapshot")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.snapshot")
    # No sibling adapter/driver and no conformance harness.
    assert not _import_ok(python, "parallax.postgres")
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "psycopg")


def test_core_snapshot_and_postgres(tmp_path: Path, wheelhouse: Wheelhouse) -> None:
    python = _make_venv(tmp_path / "venv")
    _install(python, wheelhouse, "parallax-snapshot", "parallax-postgres")

    assert _import_ok(python, "parallax.core")
    assert _import_ok(python, "parallax.snapshot")
    assert _import_ok(python, "parallax.postgres")
    assert _dist_installed(python, "psycopg")
    # The dev-only conformance tooling and container tooling stay out.
    assert not _import_ok(python, "parallax.conformance")
    assert not _dist_installed(python, "testcontainers")
    assert not _dist_installed(python, "parallax-conformance")
