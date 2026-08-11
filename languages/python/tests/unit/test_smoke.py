"""Smoke tests: the five namespace distributions import cleanly."""

from __future__ import annotations

import importlib
import importlib.util
import json
import pkgutil
import subprocess
import sys

import pytest

import parallax.conformance
import parallax.core
import parallax.descriptor
import parallax.postgres
import parallax.snapshot
from _support.distributions import TOP_PACKAGE_NAMES
from _support.repo import PY_ROOT
from parallax.conformance import cli

_PUBLIC_API_SNAPSHOT = PY_ROOT / "tests" / "api" / "public_api.json"


def test_top_package_public_surfaces() -> None:
    # `parallax.core` publishes the model-definition surface; the concrete
    # Postgres adapter surface and the snapshot developer surface
    # (`Snapshot[T]` and the execution-provenance subset, §8) are published
    # alongside `connect()`.
    assert {"Entity", "ValueObject", "Attr", "Rel", "attr", "rel", "DomainModel"} <= set(
        parallax.core.__all__
    )
    assert "meta" not in parallax.core.__all__
    assert set(parallax.snapshot.__all__) == {
        "connect",
        "Snapshot",
        "ReadTrace",
        "DatabaseCall",
        "ExecutionLog",
        "TransactionAttempt",
        "TransactionResult",
        "TransactionInProgressError",
        "TransactionNotCommittedError",
        "DeferredFeatureError",
        "KEYED_WRITE_VALUE_CODES",
        "KeyedWriteValueError",
        "NoResultFound",
        "QueryTargetError",
        "SnapshotConnectionError",
        "SnapshotDecodingError",
        "SnapshotInspectionError",
        "SnapshotMaterializationError",
        "TooManyResultsFound",
        "TransactionOwnershipError",
        "UnloadedRelationshipError",
        "is_view_loaded",
        "view",
        "pin_of",
        "edge_of",
    }
    # §8 topology fixes the adapter's public export as PostgresAdapter alone;
    # psycopg bind mechanics (Jsonb) stay internal to the adapter.
    assert set(parallax.postgres.__all__) == {"PostgresAdapter"}
    # §8 pins the Descriptor Frontend's surface closed, so the committed
    # public-API snapshot is the authority for it rather than a second list.
    descriptor_surface = json.loads(_PUBLIC_API_SNAPSHOT.read_text())["parallax.descriptor"]
    assert set(parallax.descriptor.__all__) == set(descriptor_surface)
    assert parallax.conformance.__all__ == []


def test_every_scope_submodule_imports() -> None:
    """Every enforcement-scope skeleton under the five packages imports cleanly."""
    imported: list[str] = []
    for name in TOP_PACKAGE_NAMES:
        spec = importlib.util.find_spec(name)
        assert spec is not None
        assert spec.submodule_search_locations is not None
        search_path = list(spec.submodule_search_locations)
        for info in pkgutil.walk_packages(search_path, prefix=f"{name}."):
            importlib.import_module(info.name)
            imported.append(info.name)
    # Sanity: the core spine skeleton alone contributes many scopes.
    assert "parallax.core.base" in imported
    assert "parallax.core.predicate" in imported
    assert "parallax.descriptor._ingest" in imported
    assert "parallax.snapshot.materialize" in imported
    assert "parallax.postgres.adapter" in imported
    assert "parallax.conformance.cli" in imported


@pytest.mark.parametrize(
    "module",
    ["parallax.snapshot", "parallax.snapshot.handle", "parallax.snapshot.handle._materializer"],
)
def test_snapshot_imports_cold_in_a_fresh_interpreter(module: str) -> None:
    # The in-process checks above cannot see an import cycle: by the time they
    # run, pytest collection has already imported `parallax.snapshot`, so a
    # partially-initialized-module failure is masked. `handle._materializer` imports
    # `parallax.snapshot.materialize` back through the parent package — the shape
    # that breaks only on a cold import, and only for some entry points, so each
    # entry point gets its own probe.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_conformance_cli_describe_exits_ok(capsys: pytest.CaptureFixture[str]) -> None:
    # The wire surface: `describe` emits its claim envelope.
    assert cli.main(["describe"]) == 0
    assert '"command": "describe"' in capsys.readouterr().out
