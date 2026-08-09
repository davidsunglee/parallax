"""Regression guards for the contracted Python frontend surface.

Every assertion here restates a property the landed tree already has, so nothing
in this module is a specification of new behavior. They are collected in one
place because each one is otherwise invisible: a deleted symbol coming back, a
second planner composition root, or one more Snapshot reach into a private
Entity module all pass every other gate. Failures read as "this came back",
not "this is broken".

The reaches this module pins are the ones `spec/python.md` §7 names. A new
reach is a §7 decision before it is a code change, which is what the exact-set
assertions below make true rather than merely intended.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from _support.distributions import PRODUCTION_PACKAGES, TOP_PACKAGE_DIR
from _support.repo import PY_ROOT
from parallax.core.unit_work import NO_AUDIT, PlannedWrite, SubjectIdentity, TransactionInstant

_PACKAGES = PY_ROOT / "packages"
_SNAPSHOT_SRC = _PACKAGES / "parallax-snapshot" / "src" / "parallax" / "snapshot"
_ENTITY_SRC = _PACKAGES / "parallax-core" / "src" / "parallax" / "core" / "entity"


def _sources(*roots: Path) -> Iterator[tuple[Path, str]]:
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            yield path, path.read_text(encoding="utf-8")


def _production_sources() -> Iterator[tuple[Path, str]]:
    yield from _sources(
        *(_PACKAGES / name / "src" / TOP_PACKAGE_DIR[name] for name in PRODUCTION_PACKAGES)
    )


def _hits(pattern: str, sources: Iterator[tuple[Path, str]]) -> list[str]:
    """Every ``path:line`` a word-boundary ``pattern`` matches."""
    word = re.compile(rf"\b{pattern}\b")
    return [
        f"{path.relative_to(PY_ROOT)}:{number}"
        for path, text in sources
        for number, line in enumerate(text.splitlines(), 1)
        if word.search(line)
    ]


# --------------------------------------------------------------------------- #
# Snapshot's reaches into `parallax.core.entity`.                             #
# --------------------------------------------------------------------------- #
# The enforcement unit is the scope, not a package's `__all__`, so a granted
# `parallax.core.entity` edge reaches its private modules too (`python.md` §7).
# That makes the reaches a review question rather than a gate question, and this
# is where the review's answer is written down: the exact set, per module.
ACCEPTED_PRIVATE_ENTITY_REACHES: dict[str, frozenset[str]] = {
    "_declaration": frozenset({"declaration_of", "is_entity_class", "members_of"}),
    "_entity": frozenset({"wire_names_of"}),
    "_graph_input": frozenset(
        {
            "EntityAttributeInput",
            "ValueObjectAttributeInput",
            "ValueObjectOccurrenceInput",
            "ValueObjectRecord",
        }
    ),
    "_model": frozenset({"class_index", "model_of"}),
    "_query": frozenset(
        {"FindQuery", "LoweredFindQuery", "lower_find_query", "mutation_selection"}
    ),
}


def _private_entity_reaches() -> dict[str, set[str]]:
    reached: dict[str, set[str]] = {}
    for _path, text in _sources(_SNAPSHOT_SRC):
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            prefix, _, submodule = node.module.rpartition(".")
            if prefix != "parallax.core.entity" or not submodule.startswith("_"):
                continue
            reached.setdefault(submodule, set()).update(alias.name for alias in node.names)
    return reached


def test_snapshots_private_entity_reaches_are_exactly_the_accepted_seams() -> None:
    assert _private_entity_reaches() == {
        module: set(names) for module, names in ACCEPTED_PRIVATE_ENTITY_REACHES.items()
    }


def _snapshot_imported_names() -> set[str]:
    """Every name `parallax.snapshot`'s production modules import, however spelled."""
    imported: set[str] = set()
    for _path, text in _sources(_SNAPSHOT_SRC):
        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.ImportFrom):
                imported.update(alias.asname or alias.name for alias in node.names)
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.Import):
                imported.update(alias.name.partition(".")[0] for alias in node.names)
    return imported


def test_snapshot_derives_every_row_through_the_codec_alone() -> None:
    # The row-derivation half of the same boundary: Snapshot asks the Entity Row
    # Codec for a row and reconstructs none of what the codec does. Pydantic, the
    # private Change Record slot, the exported side table, and the module-level
    # row helpers COR-63 deleted are each un-imported here — the codec's own
    # audit-neutrality proof (`test_row_codec.py`) is what makes that enough.
    # Stated over IMPORTS, because `self._codec.full_row(...)` is the codec being
    # consulted and a free `full_row` would be Snapshot deriving its own row.
    imported = _snapshot_imported_names()
    assert imported.isdisjoint(
        {
            "pydantic",
            "BaseModel",
            "CHANGE_RECORD_SLOT",
            "WireNames",
            "full_row",
            "primary_key_row",
            "canonical_row",
            "changed_fields",
            "effective_change_set",
        }
    )
    assert "row_codec_of" in imported
    assert _hits("model_fields_set", _sources(_SNAPSHOT_SRC)) == []


def test_no_snapshot_module_catches_the_codecs_own_refusal() -> None:
    # A codec refusal reports first-party misuse, so nothing may catch, wrap, or
    # rethrow one: every keyed-write refusal a developer can provoke is decided
    # from the value's provenance before a row is derived (`m-unit-work`). The
    # class is nameable in prose — two docstrings explain what is NOT caught —
    # and the guard is that it is neither imported nor handled.
    assert "EntityRowError" not in _snapshot_imported_names()
    handlers = [
        f"{path.relative_to(PY_ROOT)}:{node.lineno}"
        for path, text in _sources(_SNAPSHOT_SRC)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.ExceptHandler)
    ]
    assert len(handlers) == 2, handlers


def test_the_snapshot_path_carries_no_transition_vocabulary() -> None:
    # A name claiming its own impermanence outlives whatever left it, so the
    # absence is the guard rather than any one deletion.
    for forbidden in (
        "temporary",
        "temporarily",
        "transition",
        "transitional",
        "legacy",
        "shim",
        "deprecated",
        "placeholder",
    ):
        sources = _sources(_SNAPSHOT_SRC)
        word = re.compile(rf"\b{forbidden}\b", re.IGNORECASE)
        assert [
            f"{path.relative_to(PY_ROOT)}:{number}"
            for path, text in sources
            for number, line in enumerate(text.splitlines(), 1)
            if word.search(line)
        ] == [], forbidden


# --------------------------------------------------------------------------- #
# Surfaces earlier tickets removed, and the ones this one un-exported.        #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "removed",
    [
        "EntityRegistry",
        "ScopedMetamodel",
        "default_registry",
        "parent_registry",
        "ModelCopyError",
        "ProvenanceError",
        "FrameworkOwnedAxisError",
        "MetamodelBinding",
        "FlushPlan",
        "MilestonePlan",
    ],
)
def test_a_removed_frontend_surface_stays_removed(removed: str) -> None:
    assert _hits(removed, _production_sources()) == []


def test_the_transition_query_statement_module_stays_absent() -> None:
    assert not (_ENTITY_SRC / "statement.py").exists()
    assert _hits("Statement", _sources(_SNAPSHOT_SRC)) == []


@pytest.mark.parametrize(
    "unexported", ["EntityMeta", "ValueObjectMeta", "WireNames", "wire_names_of"]
)
def test_an_un_exported_entity_view_is_absent_from_the_package_surface(unexported: str) -> None:
    # Each name survives as implementation detail — two are metaclasses that
    # cannot be deleted — so the guard is the export, not the declaration.
    from parallax.core import entity

    assert unexported not in entity.__all__
    assert _hits(unexported, _sources(_ENTITY_SRC / "__init__.py")) == []


# --------------------------------------------------------------------------- #
# One planner, wired once, decorating nothing.                                #
# --------------------------------------------------------------------------- #
def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # Lane equivalence is structural rather than parallel wiring: the developer
    # path and the conformance lane call one factory, so a second construction
    # anywhere is a second set of strategies that could drift.
    constructions = [
        f"{path.relative_to(PY_ROOT)}:{number}"
        for path, text in _sources(_PACKAGES)
        for number, line in enumerate(text.splitlines(), 1)
        if "WritePlanner(" in line
    ]
    assert len(constructions) == 1, constructions
    assert "handle/_planning.py" in constructions[0], constructions


def test_the_write_path_decorates_no_audit_provenance() -> None:
    # Audit decoration is a wired port with nothing behind it, so no write path
    # emits an audit value — a criterion that holds whether or not the audit
    # program has landed, because decoration is downstream of everything here.
    planning = _PACKAGES / "parallax-snapshot" / "src" / "parallax" / "snapshot" / "handle"
    assert _hits("NO_AUDIT", _sources(planning / "_planning.py")) != []
    assert _hits("audit=NO_AUDIT", _sources(planning / "_planning.py")) != []
    step = cast("PlannedWrite", object())
    assert (
        NO_AUDIT.decorate(
            step,
            subject_identity=cast("SubjectIdentity", "unattributed"),
            transaction_instant=cast("TransactionInstant", None),
        )
        is step
    )
