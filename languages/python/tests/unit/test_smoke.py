"""Phase 1 smoke tests: the four namespace distributions import cleanly."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil

import pytest

import parallax.conformance
import parallax.core
import parallax.postgres
import parallax.snapshot
from parallax.conformance import cli

pytestmark = pytest.mark.unit

_TOP_PACKAGE_NAMES: tuple[str, ...] = (
    "parallax.core",
    "parallax.snapshot",
    "parallax.postgres",
    "parallax.conformance",
)


def test_top_packages_expose_empty_public_surface() -> None:
    # Phase 1 is a skeleton: no distribution exports anything yet.
    assert parallax.core.__all__ == []
    assert parallax.snapshot.__all__ == []
    assert parallax.postgres.__all__ == []
    assert parallax.conformance.__all__ == []


def test_every_scope_submodule_imports() -> None:
    """Every enforcement-scope skeleton under the four packages imports cleanly."""
    imported: list[str] = []
    for name in _TOP_PACKAGE_NAMES:
        spec = importlib.util.find_spec(name)
        assert spec is not None
        assert spec.submodule_search_locations is not None
        search_path = list(spec.submodule_search_locations)
        for info in pkgutil.walk_packages(search_path, prefix=f"{name}."):
            importlib.import_module(info.name)
            imported.append(info.name)
    # Sanity: the core spine skeleton alone contributes many scopes.
    assert "parallax.core.base" in imported
    assert "parallax.core.op_algebra" in imported
    assert "parallax.snapshot.materialize" in imported
    assert "parallax.postgres.adapter" in imported
    assert "parallax.conformance.cli" in imported


def test_conformance_cli_entrypoint_is_a_usage_stub() -> None:
    # The console-script entry point exists; the wire surface lands in Phase 2,
    # so it reports a CLI usage error (exit code 2) for now.
    assert cli.main() == 2
