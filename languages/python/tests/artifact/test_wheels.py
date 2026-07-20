"""Built-wheel content and public-export health (§8 / §10 `artifact` marker)."""

from __future__ import annotations

import zipfile

import pytest

from conftest import PRODUCTION_PACKAGES, Wheelhouse

pytestmark = pytest.mark.artifact

# Each distribution's top regular package under the shared PEP 420 namespace.
_TOP_PACKAGE_DIR: dict[str, str] = {
    "parallax-core": "parallax/core",
    "parallax-snapshot": "parallax/snapshot",
    "parallax-postgres": "parallax/postgres",
    "parallax-conformance": "parallax/conformance",
}


def _names(wheelhouse: Wheelhouse, package: str) -> list[str]:
    with zipfile.ZipFile(wheelhouse.wheels[package]) as archive:
        return archive.namelist()


def test_no_namespace_root_init_in_any_wheel(wheelhouse: Wheelhouse) -> None:
    # PEP 420: the shared `parallax` namespace root must never carry __init__.py.
    for package in wheelhouse.wheels:
        assert "parallax/__init__.py" not in _names(wheelhouse, package)


def test_each_wheel_ships_py_typed(wheelhouse: Wheelhouse) -> None:
    for package, top in _TOP_PACKAGE_DIR.items():
        assert f"{top}/py.typed" in _names(wheelhouse, package)


def test_production_wheels_exclude_conformance_and_tests(wheelhouse: Wheelhouse) -> None:
    for package in PRODUCTION_PACKAGES:
        names = _names(wheelhouse, package)
        assert not any(n.startswith("parallax/conformance/") for n in names), package
        assert not any(n.startswith("tests/") or "/tests/" in n for n in names), package
        # No stray sibling namespaces leak into a production wheel.
        own = _TOP_PACKAGE_DIR[package]
        code = [n for n in names if n.startswith("parallax/") and n.endswith(".py")]
        assert code, package
        assert all(n.startswith(f"{own}/") for n in code), package


def test_core_wheel_contains_spine_scopes(wheelhouse: Wheelhouse) -> None:
    names = _names(wheelhouse, "parallax-core")
    assert "parallax/core/__init__.py" in names
    assert "parallax/core/base/__init__.py" in names
    assert "parallax/core/op_algebra/__init__.py" in names


def test_snapshot_wheel_ships_handle_package(wheelhouse: Wheelhouse) -> None:
    # The checks above see `parallax/snapshot` only at the top-package prefix, so
    # they cannot tell a handle.py from a handle/ directory. Hatch discovers the
    # tree rather than enumerating modules, which makes the absent old path the
    # load-bearing half: it is what would catch a stale build or a half-applied
    # split. Grows to the full private-module list as the extraction proceeds.
    names = _names(wheelhouse, "parallax-snapshot")
    assert "parallax/snapshot/handle/__init__.py" in names
    assert "parallax/snapshot/handle/_family.py" in names
    assert "parallax/snapshot/handle/_keyed_sql.py" in names
    assert "parallax/snapshot/handle/_predicate_writes.py" in names
    assert "parallax/snapshot/handle/_read.py" in names
    assert "parallax/snapshot/handle/_transaction.py" in names
    assert "parallax/snapshot/handle/_wrap.py" in names
    assert "parallax/snapshot/handle/_write_inputs.py" in names
    assert "parallax/snapshot/handle/_write_lowering.py" in names
    assert "parallax/snapshot/handle/_write_types.py" in names
    assert "parallax/snapshot/handle.py" not in names
    # `wrap.py` moved INTO the package rather than being copied; a wheel carrying
    # both would mean two live copies of `wrap_graph`.
    assert "parallax/snapshot/wrap.py" not in names


def test_conformance_wheel_declares_console_script(wheelhouse: Wheelhouse) -> None:
    with zipfile.ZipFile(wheelhouse.wheels["parallax-conformance"]) as archive:
        entry_points = next(
            n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")
        )
        text = archive.read(entry_points).decode()
    assert "[console_scripts]" in text
    assert "parallax-conformance = parallax.conformance.cli:main" in text
