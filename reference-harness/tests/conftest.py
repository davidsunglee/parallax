"""Fixtures shared across the harness suite."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATE_GRAPH_FIXTURES = Path(__file__).parent / "fixtures" / "gate-graphs"


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository checkout this harness lives in."""
    return _REPO_ROOT


@pytest.fixture
def gate_graph_dir(tmp_path: Path) -> Callable[[str], Path]:
    """Copy a named ``fixtures/gate-graphs`` justfile into a scratch directory
    under the filename ``just`` discovers, and return that directory."""

    def prepare(fixture: str) -> Path:
        shutil.copyfile(_GATE_GRAPH_FIXTURES / fixture, tmp_path / "justfile")
        return tmp_path

    return prepare
