"""Smoke tests: the five namespace distributions import cleanly."""

from __future__ import annotations

import importlib
import subprocess
import sys

import psycopg
import pytest

from parallax.conformance import cli
from tests._support.distributions import DISTRIBUTION_ROOTS, importable_submodules


def test_every_scope_submodule_imports() -> None:
    """Every enforcement-scope skeleton under the five packages imports cleanly."""
    imported: list[str] = []
    for name in DISTRIBUTION_ROOTS.values():
        for module in importable_submodules(name):
            importlib.import_module(module)
            imported.append(module)
    # Sanity: the core spine skeleton alone contributes many scopes.
    assert "parallax.core.base" in imported
    assert "parallax.core.predicate" in imported
    assert "parallax.descriptor._ingest" in imported
    assert "parallax.snapshot._publication" in imported
    assert "parallax.postgres.adapter" in imported
    assert f"parallax.postgres._cloaders_{psycopg.pq.__impl__}" in imported
    assert "parallax.conformance.cli" in imported


@pytest.mark.parametrize(
    "module",
    [
        "parallax.snapshot",
        "parallax.snapshot._handle",
        "parallax.snapshot._publication",
        "parallax.snapshot._publication._wire",
        "parallax.snapshot._publication._wire_render",
        "parallax.core.read_delivery",
        "parallax.core.read_delivery._page",
        "parallax.core.execution",
        "parallax.core.unit_work",
        "parallax.core._execution._retention",
        "parallax.core._execution._transaction._runner",
        "parallax.core._execution._unit_work.uow",
    ],
)
def test_snapshot_imports_cold_in_a_fresh_interpreter(module: str) -> None:
    # The in-process checks above cannot see an import cycle: by the time they
    # run, pytest collection has already imported `parallax.snapshot`, so a
    # partially-initialized-module failure is masked. The Snapshot publication
    # package and the Page child it reads each import through a parent package
    # whose own interface imports back into them — the shape that breaks only on
    # a cold import, and only for some entry points, so each entry point gets
    # its own probe.
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"], capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr


def test_conformance_cli_describe_exits_ok(capsys: pytest.CaptureFixture[str]) -> None:
    # The wire surface: `describe` emits its claim envelope.
    assert cli.main(["describe"]) == 0
    assert '"command": "describe"' in capsys.readouterr().out
