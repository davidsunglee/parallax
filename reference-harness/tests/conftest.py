"""Fixtures shared across the harness suite, and the scheduling partition."""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from reference_harness.gate_graph import GateGraph, load_graph

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GATE_GRAPH_FIXTURES = Path(__file__).parent / "fixtures" / "gate-graphs"

# The designated entry points to a live database. A test reaching one by any other
# route would be classified `dbfree` while needing a container.
_DATABASE_FIXTURES = frozenset({"provider"})


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Assign each collected item its scheduling class.

    The class is read off the item's resolved fixture closure rather than
    authored beside the test, so it covers indirect requests, is decided per
    item rather than per module, and can be neither absent nor doubled. An item
    that is not a test function requests no fixture and is therefore `dbfree`.
    """
    for item in items:
        closure = item.fixturenames if isinstance(item, pytest.Function) else ()
        needs_database = bool(_DATABASE_FIXTURES.intersection(closure))
        item.add_marker(pytest.mark.db if needs_database else pytest.mark.dbfree)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    """The repository checkout this harness lives in."""
    return _REPO_ROOT


@pytest.fixture(scope="session")
def gate_graph_dir(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], Path]:
    """A scratch directory holding a named ``fixtures/gate-graphs`` justfile under
    the filename ``just`` discovers.

    The copy happens once per fixture file and is then shared, because nothing
    reading a gate graph writes to it.
    """
    prepared: dict[str, Path] = {}

    def prepare(fixture: str) -> Path:
        directory = prepared.get(fixture)
        if directory is None:
            directory = tmp_path_factory.mktemp(fixture.replace(".", "-"))
            shutil.copyfile(_GATE_GRAPH_FIXTURES / fixture, directory / "justfile")
            prepared[fixture] = directory
        return directory

    return prepare


@pytest.fixture(scope="session")
def gate_graph(gate_graph_dir: Callable[[str], Path]) -> Callable[[str], GateGraph]:
    """The resolved graph of a named ``fixtures/gate-graphs`` justfile, spawning
    the orchestrator once per fixture file for the whole session."""
    resolved: dict[str, GateGraph] = {}

    def load(fixture: str) -> GateGraph:
        graph = resolved.get(fixture)
        if graph is None:
            graph = load_graph(gate_graph_dir(fixture))
            resolved[fixture] = graph
        return graph

    return load


@pytest.fixture(scope="session")
def repository_graph(repo_root: Path) -> GateGraph:
    """The resolved graph of this repository's own root justfile."""
    return load_graph(repo_root)
