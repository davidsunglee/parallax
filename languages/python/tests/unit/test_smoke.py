"""Phase 1 smoke tests: the four namespace distributions import cleanly."""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import subprocess
import sys

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


def test_top_package_public_surfaces() -> None:
    # Phase 3 publishes the model-definition surface on parallax.core; Phase 5 adds
    # the concrete Postgres adapter surface. Phase 7 increment 6a publishes the
    # snapshot developer surface (`Snapshot[T]` / `Execution`, §8) alongside
    # `connect()`.
    assert {"Entity", "Field", "Relationship", "Attr", "Rel"} <= set(parallax.core.__all__)
    assert "meta" not in parallax.core.__all__
    assert set(parallax.snapshot.__all__) == {
        "connect",
        "Snapshot",
        "Execution",
        "NoResultFound",
        "TooManyResultsFound",
    }
    # §8 topology fixes the adapter's public export as PostgresAdapter alone;
    # psycopg bind mechanics (Jsonb) stay internal to the adapter.
    assert set(parallax.postgres.__all__) == {"PostgresAdapter"}
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


@pytest.mark.parametrize(
    "module",
    ["parallax.snapshot", "parallax.snapshot.handle", "parallax.snapshot.handle._wrap"],
)
def test_snapshot_imports_cold_in_a_fresh_interpreter(module: str) -> None:
    # The in-process checks above cannot see an import cycle: by the time they
    # run, pytest collection has already imported `parallax.snapshot`, so a
    # partially-initialized-module failure is masked. `handle._wrap` imports
    # `parallax.snapshot.materialize` back through the parent package — the shape
    # that breaks only on a cold import, and only for some entry points, so each
    # entry point gets its own probe.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_conformance_cli_describe_exits_ok(capsys: pytest.CaptureFixture[str]) -> None:
    # The wire surface landed in Phase 2: `describe` emits its claim envelope.
    assert cli.main(["describe"]) == 0
    assert '"command": "describe"' in capsys.readouterr().out
