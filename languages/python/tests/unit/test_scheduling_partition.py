"""The scheduling partition, and the layout it is orthogonal to.

Every collected item's class is derived from its fixture closure by the
collection hook in ``tests/conftest.py``, so neither zero nor two classes is
representable — provided the derivation stays the only source, which is what the
authored-marker check below pins. The remaining assertions grade the real
session rather than a synthetic one: whichever selection is running, every item
it holds is graded.
"""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path

import pytest

from _support.repo import PY_ROOT, REPO_ROOT
from check_database_access import ENTRY_POINT_FIXTURE

SCHEDULING_CLASSES = frozenset({"dbfree", "db"})
DATABASE_FIXTURES = frozenset({ENTRY_POINT_FIXTURE})
ORTHOGONAL_SELECTORS = frozenset({"compile_sweep", "adapter_smoke"})

# The primary semantic surfaces, each one directory under `tests/`.
SURFACES = frozenset(
    {"api", "compatibility", "dialect", "distribution", "provider_contract", "unit"}
)

TESTS_ROOT = PY_ROOT / "tests"


def _test_modules() -> list[Path]:
    return sorted(p for p in TESTS_ROOT.rglob("*.py") if "__pycache__" not in p.parts)


def _authored_marks(source: str) -> set[str]:
    """Every ``pytest.mark.<name>`` spelled in *source*."""
    marks: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Attribute):
            continue
        namespace = node.value
        if (
            isinstance(namespace.value, ast.Name)
            and namespace.value.id == "pytest"
            and namespace.attr == "mark"
        ):
            marks.add(node.attr)
    return marks


def _classes_of(item: pytest.Item) -> set[str]:
    return {mark.name for mark in item.iter_markers()} & SCHEDULING_CLASSES


# --------------------------------------------------------------------------
# The partition
# --------------------------------------------------------------------------
def test_every_collected_item_carries_exactly_one_scheduling_class(
    request: pytest.FixtureRequest,
) -> None:
    offenders = {
        item.nodeid: sorted(_classes_of(item))
        for item in request.session.items
        if len(_classes_of(item)) != 1
    }
    assert offenders == {}


def test_an_items_class_agrees_with_its_fixture_closure(
    request: pytest.FixtureRequest,
) -> None:
    for item in request.session.items:
        closure = item.fixturenames if isinstance(item, pytest.Function) else ()
        needs_database = bool(DATABASE_FIXTURES.intersection(closure))
        expected = {"db"} if needs_database else {"dbfree"}
        assert _classes_of(item) == expected, item.nodeid


def test_only_the_derivation_names_a_scheduling_class() -> None:
    # A module authoring a class would restore the second source of truth the
    # derivation exists to remove, and could give one item two classes.
    offenders = {
        path.relative_to(TESTS_ROOT).as_posix(): sorted(
            _authored_marks(path.read_text(encoding="utf-8")) & SCHEDULING_CLASSES
        )
        for path in _test_modules()
        if path.name != "conftest.py"
        and _authored_marks(path.read_text(encoding="utf-8")) & SCHEDULING_CLASSES
    }
    assert offenders == {}


def test_the_marker_catalog_is_the_partition_plus_the_orthogonal_selectors() -> None:
    config = tomllib.loads((PY_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    catalog = config["tool"]["pytest"]["ini_options"]["markers"]
    names = {entry.split(":", 1)[0] for entry in catalog}
    assert names == SCHEDULING_CLASSES | ORTHOGONAL_SELECTORS


# --------------------------------------------------------------------------
# The semantic surfaces the partition cuts across
# --------------------------------------------------------------------------
def test_the_test_root_holds_only_surfaces_support_and_runner_required_files() -> None:
    entries = {p.name for p in TESTS_ROOT.iterdir() if p.name != "__pycache__"}
    assert entries == SURFACES | {"_support", "conftest.py"}


def test_every_collected_item_sits_under_a_primary_surface(
    request: pytest.FixtureRequest,
) -> None:
    surfaces = {
        Path(str(item.path)).relative_to(TESTS_ROOT).parts[0] for item in request.session.items
    }
    assert surfaces <= SURFACES


def test_each_focused_surface_recipe_selects_its_own_directory() -> None:
    justfile = (REPO_ROOT / "justfile").read_text(encoding="utf-8")
    for surface in sorted(SURFACES):
        recipe = f"python-test-{surface.replace('_', '-')}"
        match = re.search(rf"^{re.escape(recipe)}:\n((?:    .*\n)+)", justfile, re.MULTILINE)
        assert match is not None, f"no recipe `{recipe}`"
        (invocation,) = match.group(1).strip().splitlines()
        assert invocation.endswith(f"uv run pytest tests/{surface}")
