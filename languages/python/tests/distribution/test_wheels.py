"""Built-wheel content and public-export health (§8 / §10 `artifact` marker)."""

from __future__ import annotations

import subprocess
import tarfile
import zipfile
from pathlib import Path

from _support.distributions import PRODUCTION_PACKAGES, TOP_PACKAGE_DIR, Wheelhouse
from _support.repo import PY_ROOT, REPO_ROOT

_PACKAGED_SCHEMA = "parallax/descriptor/_schemas/metamodel.schema.json"


def _names(wheelhouse: Wheelhouse, package: str) -> list[str]:
    with zipfile.ZipFile(wheelhouse.wheels[package]) as archive:
        return archive.namelist()


def test_no_namespace_root_init_in_any_wheel(wheelhouse: Wheelhouse) -> None:
    # PEP 420: the shared `parallax` namespace root must never carry __init__.py.
    for package in wheelhouse.wheels:
        assert "parallax/__init__.py" not in _names(wheelhouse, package)


def test_each_wheel_ships_py_typed(wheelhouse: Wheelhouse) -> None:
    for package, top in TOP_PACKAGE_DIR.items():
        assert f"{top}/py.typed" in _names(wheelhouse, package)


def test_production_wheels_exclude_conformance_and_tests(wheelhouse: Wheelhouse) -> None:
    for package in PRODUCTION_PACKAGES:
        names = _names(wheelhouse, package)
        assert not any(n.startswith("parallax/conformance/") for n in names), package
        assert not any(n.startswith("tests/") or "/tests/" in n for n in names), package
        # No stray sibling namespaces leak into a production wheel.
        own = TOP_PACKAGE_DIR[package]
        code = [n for n in names if n.startswith("parallax/") and n.endswith(".py")]
        assert code, package
        assert all(n.startswith(f"{own}/") for n in code), package


def test_core_wheel_contains_spine_scopes(wheelhouse: Wheelhouse) -> None:
    names = _names(wheelhouse, "parallax-core")
    assert "parallax/core/__init__.py" in names
    assert "parallax/core/base/__init__.py" in names
    assert "parallax/core/predicate/__init__.py" in names


def test_core_wheel_ships_sql_gen_package(wheelhouse: Wheelhouse) -> None:
    # Same idiom, same reasoning as the handle package below: Hatch discovers the
    # tree rather than enumerating modules, so the ABSENT `sql_gen/compile.py` is
    # the load-bearing half — every required path below would still pass against a
    # tree that kept the old single-file compiler beside the split, which is
    # exactly what a stale build or a half-applied split looks like. This is the
    # complete package — the five private modules plus the
    # re-exporting interface, and nothing else.
    names = _names(wheelhouse, "parallax-core")
    assert "parallax/core/sql_gen/__init__.py" in names
    assert "parallax/core/sql_gen/_compile.py" in names
    assert "parallax/core/sql_gen/_context.py" in names
    assert "parallax/core/sql_gen/_inheritance.py" in names
    assert "parallax/core/sql_gen/_navigation.py" in names
    assert "parallax/core/sql_gen/_predicate.py" in names
    assert "parallax/core/sql_gen/compile.py" not in names


def test_snapshot_wheel_ships_handle_package(wheelhouse: Wheelhouse) -> None:
    # The checks above see `parallax/snapshot` only at the top-package prefix, so
    # they cannot tell a handle.py from a handle/ directory. Hatch discovers the
    # tree rather than enumerating modules, which makes the absent old path the
    # load-bearing half: it is what would catch a stale build or a half-applied
    # split. This is the complete package — the seventeen private
    # modules plus the re-exporting interface.
    names = _names(wheelhouse, "parallax-snapshot")
    assert "parallax/snapshot/handle/__init__.py" in names
    assert "parallax/snapshot/handle/_database.py" in names
    assert "parallax/snapshot/handle/_errors.py" in names
    assert "parallax/snapshot/handle/_family.py" in names
    assert "parallax/snapshot/handle/_features.py" in names
    assert "parallax/snapshot/handle/_keyed_sql.py" in names
    assert "parallax/snapshot/handle/_materializer.py" in names
    assert "parallax/snapshot/handle/_planning.py" in names
    assert "parallax/snapshot/handle/_predicate_writes.py" in names
    assert "parallax/snapshot/handle/_preflight.py" in names
    assert "parallax/snapshot/handle/_read.py" in names
    assert "parallax/snapshot/handle/_stream.py" in names
    assert "parallax/snapshot/handle/_transaction.py" in names
    assert "parallax/snapshot/handle/_wire.py" in names
    assert "parallax/snapshot/handle/_wire_writes.py" in names
    assert "parallax/snapshot/handle/_write_inputs.py" in names
    assert "parallax/snapshot/handle/_write_lowering.py" in names
    assert "parallax/snapshot/handle.py" not in names


def test_snapshot_wheel_ships_the_materialize_package(wheelhouse: Wheelhouse) -> None:
    # Same idiom, same reasoning: the ABSENT `materialize.py` is the load-bearing
    # half — every required path below would still pass against a tree that kept
    # the old single-file assembler beside the split, and a wheel carrying both
    # would mean two live copies of the conversion seam.
    names = _names(wheelhouse, "parallax-snapshot")
    assert "parallax/snapshot/materialize/__init__.py" in names
    assert "parallax/snapshot/materialize/_convert.py" in names
    assert "parallax/snapshot/materialize/_graph.py" in names
    assert "parallax/snapshot/materialize/_merge.py" in names
    assert "parallax/snapshot/materialize.py" not in names


def test_descriptor_wheel_ships_the_privatized_frontend(wheelhouse: Wheelhouse) -> None:
    # Same idiom, same reasoning as the two package checks above: Hatch discovers
    # the tree, so the ABSENT public module names are the load-bearing half — a
    # wheel still carrying `records.py` beside `_records.py` is what a stale build
    # or a half-applied move looks like, and it would also re-expose the record
    # vocabulary §8 keeps private.
    names = _names(wheelhouse, "parallax-descriptor")
    assert "parallax/descriptor/__init__.py" in names
    assert "parallax/descriptor/_adapter.py" in names
    assert "parallax/descriptor/_errors.py" in names
    assert "parallax/descriptor/_export.py" in names
    assert "parallax/descriptor/_hub.py" in names
    assert "parallax/descriptor/_ingest.py" in names
    assert "parallax/descriptor/_records.py" in names
    assert "parallax/descriptor/_relationship.py" in names
    assert "parallax/descriptor/_serde.py" in names
    assert "parallax/descriptor/_type_spelling.py" in names
    for retired in ("records", "serde", "ingest", "export", "unresolved", "errors", "relationship"):
        assert f"parallax/descriptor/{retired}.py" not in names


def test_descriptor_wheel_schema_matches_the_authoritative_source(wheelhouse: Wheelhouse) -> None:
    # `core/schemas/metamodel.schema.json` stays authoritative and the wheel
    # embeds a byte-for-byte copy, so drift between them is the only failure this
    # can report — and an installed frontend loads the copy, never a
    # repository-relative path.
    authoritative = (REPO_ROOT / "core" / "schemas" / "metamodel.schema.json").read_bytes()
    with zipfile.ZipFile(wheelhouse.wheels["parallax-descriptor"]) as archive:
        assert _PACKAGED_SCHEMA in archive.namelist()
        assert archive.read(_PACKAGED_SCHEMA) == authoritative


def test_no_other_wheel_ships_the_descriptor_schema(wheelhouse: Wheelhouse) -> None:
    for package in wheelhouse.wheels:
        if package == "parallax-descriptor":
            continue
        assert _PACKAGED_SCHEMA not in _names(wheelhouse, package), package


def test_descriptor_sdist_schema_matches_the_authoritative_source(tmp_path: Path) -> None:
    # §8 embeds the copy in the sdist too, and hatchling selects sdist and wheel
    # files independently: the wheel check above cannot speak for the sdist.
    subprocess.run(
        ["uv", "build", "--package", "parallax-descriptor", "--sdist", "--out-dir", str(tmp_path)],
        cwd=PY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    sdists = sorted(tmp_path.glob("parallax_descriptor-*.tar.gz"))
    assert len(sdists) == 1, sdists
    authoritative = (REPO_ROOT / "core" / "schemas" / "metamodel.schema.json").read_bytes()
    with tarfile.open(sdists[0]) as archive:
        member = next(
            (n for n in archive.getnames() if n.endswith(f"src/{_PACKAGED_SCHEMA}")),
            None,
        )
        assert member is not None, archive.getnames()
        packaged = archive.extractfile(member)
        assert packaged is not None
        assert packaged.read() == authoritative


def test_conformance_wheel_declares_console_script(wheelhouse: Wheelhouse) -> None:
    with zipfile.ZipFile(wheelhouse.wheels["parallax-conformance"]) as archive:
        entry_points = next(
            n for n in archive.namelist() if n.endswith(".dist-info/entry_points.txt")
        )
        text = archive.read(entry_points).decode()
    assert "[console_scripts]" in text
    assert "parallax-conformance = parallax.conformance.cli:main" in text
