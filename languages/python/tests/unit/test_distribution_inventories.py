"""Parity canary: every workspace distribution appears in every inventory that
is meant to list all of them.

Adding a distribution means spelling it into eight hand-maintained inventories
whose shapes have nothing in common — TOML requirement strings, TOML source
roots, a JSON list of type-check roots, Python tuples of distribution names, a
distribution-to-package-directory map, and a tuple of dotted root packages.
Collapsing them into one generated source would fight ``check_dag_sync``'s
ownership of its own generated block for no real gain; failing loudly when
``packages/*`` gains a member an inventory does not know about buys the same
protection. An omission is silent otherwise: a missing type-check root disables
strict checking over a whole distribution without any gate going red.

``packages/*`` is the authority, because that glob is exactly
``[tool.uv.workspace].members`` — what makes a directory a distribution at all.
Two inventories encode the production/development split rather than the full
set, so membership is asserted as "production xor development" instead of
"present in the production list".

``tests/api/public_api.json`` is deliberately not asserted per
distribution: it is keyed by public *module* surface, not by distribution. It
carries the sub-scopes ``parallax.core.metamodel`` and
``parallax.snapshot.handle`` and omits ``parallax.conformance`` entirely, whose
``__all__`` is empty. The strongest true statement about it is that every key
sits under some distribution's root package, which is what is checked here.
"""

from __future__ import annotations

import json
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import cast

import pytest

import check_dag_sync as dag
from _support.distributions import (
    ALL_PACKAGES,
    PRODUCTION_PACKAGES,
    TOP_PACKAGE_DIR,
    TOP_PACKAGE_NAMES,
)
from _support.repo import PY_ROOT

_PACKAGES_DIR = PY_ROOT / "packages"
_WORKSPACE_PYPROJECT = PY_ROOT / "pyproject.toml"
_PYRIGHT_CONFIG = PY_ROOT / "pyrightconfig.json"
_PUBLIC_API_SNAPSHOT = PY_ROOT / "tests" / "api" / "public_api.json"

_REQUIREMENT_NAME = re.compile(r"[A-Za-z0-9._-]+")


def _distributions() -> tuple[str, ...]:
    return tuple(sorted(path.name for path in _PACKAGES_DIR.iterdir() if path.is_dir()))


DISTRIBUTIONS = _distributions()


def _root_package(distribution: str) -> str:
    """The single top regular package a distribution ships under the namespace."""
    namespace = _PACKAGES_DIR / distribution / "src" / "parallax"
    tops = sorted(
        path.name for path in namespace.iterdir() if path.is_dir() and path.name != "__pycache__"
    )
    assert len(tops) == 1, f"{distribution} ships {tops}, expected one top package"
    return f"parallax.{tops[0]}"


ROOT_PACKAGES = {distribution: _root_package(distribution) for distribution in DISTRIBUTIONS}


def _toml(path: Path) -> Mapping[str, object]:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def _table(parent: Mapping[str, object], *keys: str) -> Mapping[str, object]:
    table = parent
    for key in keys:
        nested = table[key]
        assert isinstance(nested, dict), f"{key} is not a table"
        table = cast("Mapping[str, object]", nested)
    return table


def _strings(parent: Mapping[str, object], key: str) -> list[str]:
    values = parent[key]
    assert isinstance(values, list)
    listed = cast("list[object]", values)
    assert all(isinstance(value, str) for value in listed), key
    return cast("list[str]", listed)


def _requirement_names(requirements: list[str]) -> set[str]:
    named: set[str] = set()
    for requirement in requirements:
        match = _REQUIREMENT_NAME.match(requirement)
        assert match is not None, requirement
        named.add(match.group())
    return named


def _production_distributions() -> set[str]:
    project = _table(_toml(_WORKSPACE_PYPROJECT), "project")
    return _requirement_names(_strings(project, "dependencies")) & set(DISTRIBUTIONS)


def test_the_authority_is_a_nonempty_set_of_self_named_distributions() -> None:
    # Every later assertion reads `packages/*` directory names as distribution
    # names, so the two must actually agree.
    assert len(DISTRIBUTIONS) >= 5
    for distribution in DISTRIBUTIONS:
        manifest = _toml(_PACKAGES_DIR / distribution / "pyproject.toml")
        assert _table(manifest, "project")["name"] == distribution


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_every_distribution_is_a_production_or_a_development_dependency(
    distribution: str,
) -> None:
    config = _toml(_WORKSPACE_PYPROJECT)
    production = _requirement_names(_strings(_table(config, "project"), "dependencies"))
    development = _requirement_names(_strings(_table(config, "dependency-groups"), "dev"))
    assert (distribution in production) != (distribution in development), (
        f"{distribution} must be in exactly one of pyproject.toml "
        f"[project].dependencies or [dependency-groups].dev"
    )


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_every_distribution_resolves_from_the_workspace(distribution: str) -> None:
    sources = _table(_toml(_WORKSPACE_PYPROJECT), "tool", "uv", "sources")
    assert sources.get(distribution) == {"workspace": True}, (
        f"{distribution} is missing from pyproject.toml [tool.uv.sources]"
    )


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_every_distribution_source_root_is_linted(distribution: str) -> None:
    ruff = _table(_toml(_WORKSPACE_PYPROJECT), "tool", "ruff")
    assert f"packages/{distribution}/src" in _strings(ruff, "src"), (
        f"{distribution} is missing from pyproject.toml [tool.ruff].src"
    )


@pytest.mark.parametrize("distribution", DISTRIBUTIONS)
def test_every_distribution_source_root_is_type_checked(distribution: str) -> None:
    # Pyright reports nothing at all for a source root outside `include`, so an
    # omission here reads as a passing strict-mode run over unchecked code.
    config = cast("Mapping[str, object]", json.loads(_PYRIGHT_CONFIG.read_text(encoding="utf-8")))
    assert f"packages/{distribution}/src" in _strings(config, "include"), (
        f"{distribution} is missing from pyrightconfig.json include"
    )


def test_the_test_suite_package_tuples_cover_every_distribution() -> None:
    assert set(ALL_PACKAGES) == set(DISTRIBUTIONS), (
        "_support.distributions.ALL_PACKAGES does not match packages/*"
    )
    assert set(PRODUCTION_PACKAGES) == _production_distributions(), (
        "_support.distributions.PRODUCTION_PACKAGES does not match "
        "pyproject.toml [project].dependencies"
    )


def test_every_distribution_has_a_wheel_top_package_directory() -> None:
    packaged = {
        distribution: root.replace(".", "/") for distribution, root in ROOT_PACKAGES.items()
    }
    assert packaged == TOP_PACKAGE_DIR, (
        "_support.distributions.TOP_PACKAGE_DIR does not match packages/*"
    )


def test_every_root_package_is_an_import_linter_root() -> None:
    assert set(dag.ROOT_PACKAGES) == set(ROOT_PACKAGES.values()), (
        "check_dag_sync.ROOT_PACKAGES does not match packages/*"
    )


def test_every_root_package_is_import_smoke_tested() -> None:
    assert set(TOP_PACKAGE_NAMES) == set(ROOT_PACKAGES.values()), (
        "_support.distributions.TOP_PACKAGE_NAMES does not match packages/*"
    )


def test_every_public_api_surface_sits_under_a_root_package() -> None:
    roots = set(ROOT_PACKAGES.values())
    snapshot = cast(
        "Mapping[str, object]", json.loads(_PUBLIC_API_SNAPSHOT.read_text(encoding="utf-8"))
    )
    for surface in snapshot:
        root = ".".join(surface.split(".")[:2])
        assert root in roots, f"{surface} in public_api.json names no distribution"
