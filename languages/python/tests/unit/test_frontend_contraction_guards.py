"""Regression guards for the contracted Python frontend surface.

Every assertion here is a property of the frontend's shape rather than of a
caller-observable behavior, so nothing in this module specifies behavior. They
are collected in one place because each one is otherwise invisible: a deleted
symbol coming back, a second planner composition root, or one more Snapshot
reach into a private Entity module all pass every other gate. Failures read as
"this came back", not "this is broken".

The reaches this module pins are the ones `spec/python.md` §7 names. A reach §7
does not name is a §7 decision before it is a code change, which is what the
exact-set assertions below make true rather than merely intended.

Each guard is stated over the artifact it constrains — an import's SOURCE
module and bound name, a handler's caught type, a call's resolved callee, a
definition's name — rather than over a line of text, so a regression spelled
differently from the one that prompted the guard fails it just the same.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

from _support.distributions import ALL_PACKAGES, PRODUCTION_PACKAGES, TOP_PACKAGE_DIR
from _support.repo import PY_ROOT
from parallax.core.unit_work import NO_AUDIT, PlannedWrite, SubjectIdentity, TransactionInstant

_PACKAGES = PY_ROOT / "packages"
_SNAPSHOT_SRC = _PACKAGES / "parallax-snapshot" / "src" / "parallax" / "snapshot"
_ENTITY_SRC = _PACKAGES / "parallax-core" / "src" / "parallax" / "core" / "entity"

_ENTITY_PACKAGE = "parallax.core.entity"


def _sources(*roots: Path) -> Iterator[tuple[Path, str]]:
    for root in roots:
        paths = [root] if root.is_file() else sorted(root.rglob("*.py"))
        for path in paths:
            yield path, path.read_text(encoding="utf-8")


def _package_sources(names: Iterable[str]) -> Iterator[tuple[Path, str]]:
    yield from _sources(*(_PACKAGES / name / "src" / TOP_PACKAGE_DIR[name] for name in names))


def _production_sources() -> Iterator[tuple[Path, str]]:
    """Every shipped distribution's sources; the conformance tooling is not one."""
    yield from _package_sources(PRODUCTION_PACKAGES)


def _all_sources() -> Iterator[tuple[Path, str]]:
    """Every distribution's sources, the dev-only conformance tooling included."""
    yield from _package_sources(ALL_PACKAGES)


def _site(path: Path, line: int) -> str:
    return f"{path.relative_to(PY_ROOT)}:{line}"


def _dotted(path: Path) -> str:
    """A source file's importable module name."""
    src = next(parent for parent in path.parents if parent.name == "src")
    return ".".join(path.relative_to(src).with_suffix("").parts).removesuffix(".__init__")


def _hits(pattern: str, sources: Iterator[tuple[Path, str]], *, flags: int = 0) -> list[str]:
    """Every ``path:line`` the regular expression ``pattern`` matches."""
    expression = re.compile(pattern, flags)
    return [
        _site(path, number)
        for path, text in sources
        for number, line in enumerate(text.splitlines(), 1)
        if expression.search(line)
    ]


def _word(name: str) -> str:
    return rf"\b{re.escape(name)}\b"


# --------------------------------------------------------------------------- #
# Imports, modelled so that a guard can name the module an import READS from   #
# and not only the local name it binds. `from pydantic import Field` binds no  #
# name any inventory of forbidden spellings would list, and a guard stated     #
# over bound names alone therefore admits it.                                  #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _Import:
    site: str
    importer: str
    """The dotted module doing the importing."""
    source: str
    """The dotted module imported FROM; empty for a plain ``import x``."""
    name: str
    """The imported attribute, or the dotted module for a plain ``import x``."""
    local: str
    """The name the import binds in ``importer``."""

    @property
    def distribution(self) -> str:
        """The top-level package the import reads from, however it is spelled."""
        return (self.source or self.name).partition(".")[0]


def _module_imports(path: Path, tree: ast.Module) -> Iterator[_Import]:
    importer = _dotted(path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            source = "." * node.level + (node.module or "")
            for alias in node.names:
                yield _Import(
                    _site(path, node.lineno),
                    importer,
                    source,
                    alias.name,
                    alias.asname or alias.name,
                )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield _Import(
                    _site(path, node.lineno),
                    importer,
                    "",
                    alias.name,
                    alias.asname or alias.name.partition(".")[0],
                )


def _imports(sources: Iterator[tuple[Path, str]]) -> Iterator[_Import]:
    for path, text in sources:
        yield from _module_imports(path, ast.parse(text))


def _snapshot_imports() -> list[_Import]:
    return list(_imports(_sources(_SNAPSHOT_SRC)))


# --------------------------------------------------------------------------- #
# Snapshot's reaches into `parallax.core.entity`.                             #
# --------------------------------------------------------------------------- #
# The enforcement unit is the scope, not a package's `__all__`, so a granted
# `parallax.core.entity` edge reaches its private modules too (`python.md` §7).
# The accepted set is therefore an inventory rather than a gate, and the
# inventory is keyed by REACHING module: §7 grants the reach to named modules,
# so a fourth module importing an already-accepted name is a new reach and a new
# §7 decision, not a use of an existing one.
ACCEPTED_PRIVATE_ENTITY_REACHES: dict[tuple[str, str], frozenset[str]] = {
    ("parallax.snapshot._inspection", "_declaration"): frozenset(
        {"declaration_of", "is_entity_class", "members_of"}
    ),
    ("parallax.snapshot.handle._database", "_model"): frozenset({"class_index", "model_of"}),
    ("parallax.snapshot.handle._predicate_writes", "_query"): frozenset({"mutation_selection"}),
    ("parallax.snapshot.handle._preflight", "_query"): frozenset(
        {"FindQuery", "LoweredFindQuery", "lower_find_query"}
    ),
    ("parallax.snapshot.handle._write_inputs", "_declaration"): frozenset({"declaration_of"}),
    ("parallax.snapshot.handle._write_inputs", "_entity"): frozenset({"wire_names_of"}),
    ("parallax.snapshot.materialize._convert", "_graph_input"): frozenset(
        {
            "EntityAttributeInput",
            "ValueObjectAttributeInput",
            "ValueObjectOccurrenceInput",
            "ValueObjectRecord",
        }
    ),
    ("parallax.snapshot.materialize._input", "_graph_input"): frozenset(
        {"EntityAttributeInput", "ValueObjectOccurrenceInput"}
    ),
    ("parallax.snapshot.materialize._merge", "_graph_input"): frozenset(
        {"EntityAttributeInput", "ValueObjectOccurrenceInput"}
    ),
}


def _private_entity_reaches() -> dict[tuple[str, str], set[str]]:
    reached: dict[tuple[str, str], set[str]] = {}
    for imported in _snapshot_imports():
        prefix, _, submodule = imported.source.rpartition(".")
        if prefix != _ENTITY_PACKAGE or not submodule.startswith("_"):
            continue
        reached.setdefault((imported.importer, submodule), set()).add(imported.name)
    return reached


def test_snapshots_private_entity_reaches_are_exactly_the_accepted_seams() -> None:
    assert _private_entity_reaches() == {
        reach: set(names) for reach, names in ACCEPTED_PRIVATE_ENTITY_REACHES.items()
    }
    assert [
        imported.site
        for imported in _snapshot_imports()
        if not imported.source and imported.name.startswith(f"{_ENTITY_PACKAGE}._")
    ] == []


# --------------------------------------------------------------------------- #
# Row derivation: the codec answers, and Snapshot reconstructs none of it.    #
# --------------------------------------------------------------------------- #
# The free row and Change Set helpers the Entity Row Codec replaced. Absent as
# imports AND as definitions, because reintroducing one under Snapshot needs no
# import at all.
DELETED_ROW_HELPERS = frozenset(
    {"full_row", "primary_key_row", "canonical_row", "changed_fields", "effective_change_set"}
)
FORBIDDEN_ROW_IMPORTS = DELETED_ROW_HELPERS | {"BaseModel", "CHANGE_RECORD_SLOT", "WireNames"}


def test_snapshot_derives_every_row_through_the_codec_alone() -> None:
    # Snapshot asks the Entity Row Codec for a row and reconstructs no part of
    # what the codec does: not through Pydantic, not through the private Change
    # Record slot, not through the exported side table, and not through a row
    # helper of its own. The codec's own audit-neutrality proof
    # (`test_row_codec.py`) is what makes consulting it enough.
    #
    # `self._codec.full_row(...)` IS the codec being consulted, so the guard is
    # stated over what Snapshot imports and defines rather than over the call.
    imported = _snapshot_imports()
    assert [
        entry.site
        for entry in imported
        if entry.name in FORBIDDEN_ROW_IMPORTS or entry.local in FORBIDDEN_ROW_IMPORTS
    ] == []
    assert [entry.site for entry in imported if entry.distribution == "pydantic"] == []
    assert [
        entry.site
        for entry in imported
        if entry.source.startswith("parallax") and entry.name.startswith("_")
    ] == []
    assert [
        _site(path, node.lineno)
        for path, text in _sources(_SNAPSHOT_SRC)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in DELETED_ROW_HELPERS
    ] == []
    assert [
        (entry.importer, entry.source) for entry in imported if entry.name == "row_codec_of"
    ] == [("parallax.snapshot.handle._database", _ENTITY_PACKAGE)]
    assert _hits(_word("model_fields_set"), _sources(_SNAPSHOT_SRC)) == []


# Every `except` clause under `parallax.snapshot`, as the module that writes it
# and the type it names. An inventory rather than a count: swapping one accepted
# handler's type for another leaves any count unchanged, and the type is the
# whole subject of the guard below.
ACCEPTED_SNAPSHOT_EXCEPT_HANDLERS: list[tuple[str, str]] = [
    ("parallax.snapshot.handle._read", "Exception"),
    ("parallax.snapshot.materialize._convert", "LeafEncodingError"),
]


def _snapshot_except_handlers() -> list[tuple[str, str]]:
    return sorted(
        (_dotted(path), "" if node.type is None else ast.unparse(node.type))
        for path, text in _sources(_SNAPSHOT_SRC)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.ExceptHandler)
    )


def test_no_snapshot_module_catches_the_codecs_own_refusal() -> None:
    # A codec refusal reports first-party misuse, so nothing may catch, wrap, or
    # rethrow one: every keyed-write refusal a developer can provoke is decided
    # from the value's provenance before a row is derived (`m-unit-work`). The
    # class is nameable in prose — two docstrings explain what is NOT caught —
    # so the guard is that it is neither imported nor named by any handler,
    # under any spelling a handler could reach it by.
    assert [
        entry.site for entry in _snapshot_imports() if "EntityRowError" in {entry.name, entry.local}
    ] == []
    assert _snapshot_except_handlers() == ACCEPTED_SNAPSHOT_EXCEPT_HANDLERS


TRANSITION_VOCABULARY = (
    "temporary",
    "temporarily",
    "transition",
    "transitional",
    "legacy",
    "shim",
    "deprecated",
    "placeholder",
)


def test_the_snapshot_path_carries_no_transition_vocabulary() -> None:
    # A name claiming its own impermanence outlives whatever left it, so the
    # absence is the guard rather than any one deletion.
    for forbidden in TRANSITION_VOCABULARY:
        assert _hits(_word(forbidden), _sources(_SNAPSHOT_SRC), flags=re.IGNORECASE) == [], (
            forbidden
        )


# --------------------------------------------------------------------------- #
# Surfaces the registry, row/provenance, and planner contractions removed.    #
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
    assert _hits(_word(removed), _production_sources()) == []


def test_the_removed_registry_keyword_stays_absent() -> None:
    # The registry frontend's caller-visible half is the `registry=` argument,
    # which survives every guard stated over the removed type names: a parameter
    # can be reintroduced without naming `EntityRegistry` anywhere.
    assert _hits(r"\bregistry=", _all_sources()) == []


def test_the_transition_query_statement_module_stays_absent() -> None:
    assert not (_ENTITY_SRC / "statement.py").exists()
    assert _hits(rf"{_ENTITY_PACKAGE}(\.| import )statement\b", _all_sources()) == []
    assert _hits(_word("Statement"), _sources(_SNAPSHOT_SRC)) == []


@pytest.mark.parametrize(
    "unexported", ["EntityMeta", "ValueObjectMeta", "WireNames", "wire_names_of"]
)
def test_an_un_exported_entity_view_is_absent_from_the_package_surface(unexported: str) -> None:
    # Each name survives as implementation detail — two are metaclasses that
    # cannot be deleted — so the guard is that the package module neither
    # imports nor lists it. The published inventory itself is `tests/api/`'s
    # subject, against `public_api.json`.
    assert _hits(_word(unexported), _sources(_ENTITY_SRC / "__init__.py")) == []


# --------------------------------------------------------------------------- #
# One planner, wired once, decorating nothing.                                #
# --------------------------------------------------------------------------- #
def _bound_to(tree: ast.Module, source_prefix: str, name: str) -> set[str]:
    """Every local name that reaches ``source_prefix.name``, aliases included."""
    bound = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and node.module.startswith(source_prefix)
        for alias in node.names
        if alias.name == name
    }
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Name)
            and node.value.id in bound
        ):
            bound.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return bound


def _calls(tree: ast.Module, callees: set[str], attribute: str) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Name) and func.id in callees) or (
            isinstance(func, ast.Attribute) and func.attr == attribute
        ):
            yield node


def _keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


def _write_planner_constructions() -> list[tuple[str, str | None]]:
    """Every construction of the Write Planner, as its module and audit argument."""
    found: list[tuple[str, str | None]] = []
    for path, text in _all_sources():
        tree = ast.parse(text)
        bound = _bound_to(tree, "parallax.core.unit_work", "WritePlanner")
        found.extend(
            (_dotted(path), _keyword(call, "audit")) for call in _calls(tree, bound, "WritePlanner")
        )
    return sorted(found)


def _planner_definitions() -> list[str]:
    """Every class that is, or descends from, a Write Planner."""
    found: list[str] = []
    for path, text in _all_sources():
        tree = ast.parse(text)
        bound = _bound_to(tree, "parallax.core.unit_work", "WritePlanner")
        found.extend(
            f"{_dotted(path)}.{node.name}"
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and (
                node.name.endswith("Planner")
                or any(isinstance(base, ast.Name) and base.id in bound for base in node.bases)
            )
        )
    return sorted(found)


def _factory_callers() -> list[str]:
    """Every module that calls the composition-root factory."""
    found: set[str] = set()
    for path, text in _all_sources():
        tree = ast.parse(text)
        bound = _bound_to(tree, "parallax.snapshot.handle", "build_write_planner")
        if any(_calls(tree, bound, "build_write_planner")):
            found.add(_dotted(path))
    return sorted(found)


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # Lane equivalence is structural rather than parallel wiring: the developer
    # path and the conformance lane call one factory, so a second construction
    # anywhere is a second set of strategies that could drift. Stated over the
    # resolved callee rather than the spelling `WritePlanner(`, because a local
    # alias constructs the same class under a name no text search finds.
    assert _write_planner_constructions() == [("parallax.snapshot.handle._planning", "NO_AUDIT")]
    assert _planner_definitions() == ["parallax.core.unit_work.write_planner.WritePlanner"]
    assert _factory_callers() == [
        "parallax.conformance.engine",
        "parallax.snapshot.handle._database",
    ]


def _audit_arguments() -> list[tuple[str, str]]:
    return sorted(
        (_dotted(path), ast.unparse(keyword.value))
        for path, text in _all_sources()
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "audit"
    )


def test_the_write_path_decorates_no_audit_provenance() -> None:
    # Audit decoration is a wired port with nothing behind it. Three statements
    # make "no write path emits an audit value" checkable: the only audit
    # argument any distribution passes is the neutral strategy, no module under
    # Snapshot implements the decoration port, and the neutral strategy returns
    # the step it was handed.
    assert _audit_arguments() == [("parallax.snapshot.handle._planning", "NO_AUDIT")]
    assert [
        entry.site for entry in _snapshot_imports() if "AuditStrategy" in {entry.name, entry.local}
    ] == []
    assert [
        _site(path, node.lineno)
        for path, text in _sources(_SNAPSHOT_SRC)
        for node in ast.walk(ast.parse(text))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name == "decorate"
    ] == []
    step = cast("PlannedWrite", object())
    assert (
        NO_AUDIT.decorate(
            step,
            subject_identity=cast("SubjectIdentity", "unattributed"),
            transaction_instant=cast("TransactionInstant", None),
        )
        is step
    )
