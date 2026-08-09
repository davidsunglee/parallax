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

Every guard is stated over something the source decides outright: what a name
resolves to, what descends from a class, what a module imports, what a scope
declares, whether a file exists, whether a spelling occurs. Deciding a guard
that way makes it stronger and narrower at once — it catches a reconstruction
spelled differently from the one that prompted it, and it stays silent for
unrelated code that merely shares a spelling. Several guards therefore import
the distributions and ask Python, because a name's binding and a class's
ancestry are runtime facts that source text only approximates.

Three prohibitions this contraction also carries are NOT decidable that way, and
nothing here is to be read as covering them:

- a row derived from something other than the codec — assembled member by member
  out of ordinary attribute reads, or through Pydantic's V1 aliases, whose
  spellings (``dict``, ``json``, ``copy``, ``schema``, ``validate``,
  ``construct``) are ordinary Python words this package already uses for
  unrelated purposes;
- a handler typed broadly enough to catch a codec refusal without naming it,
  which is prohibited only where a codec call can actually reach it;
- an audit value stamped by hand under a name of its own.

Each asks what a value IS, or what a call at runtime REACHES, rather than how
the source spells it. Each is named again at the guard whose subject it borders,
with the kind of evidence that does decide it — which is behavioral, and lives
with the behavior rather than here.
"""

from __future__ import annotations

import ast
import builtins
import importlib
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from typing import cast

import pytest
from pydantic import BaseModel

from _support.distributions import ALL_PACKAGES, PRODUCTION_PACKAGES, TOP_PACKAGE_DIR
from _support.repo import PY_ROOT
from parallax.core.entity import EntityRowError
from parallax.core.entity._entity import CHANGE_RECORD_SLOT
from parallax.core.unit_work import (
    NO_AUDIT,
    PlannedWrite,
    SubjectIdentity,
    TransactionInstant,
    WritePlanner,
)
from parallax.snapshot.handle import build_write_planner

_PACKAGES = PY_ROOT / "packages"
_CORE_SRC = _PACKAGES / "parallax-core" / "src" / "parallax" / "core"
_SNAPSHOT_SRC = _PACKAGES / "parallax-snapshot" / "src" / "parallax" / "snapshot"
_ENTITY_SRC = _CORE_SRC / "entity"

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


def _parsed(sources: Iterator[tuple[Path, str]]) -> Iterator[tuple[Path, ast.Module]]:
    for path, text in sources:
        yield path, ast.parse(text)


def _loaded_modules(
    sources: Iterator[tuple[Path, str]],
) -> Iterator[tuple[Path, ast.Module, dict[str, object]]]:
    """Each source file, its syntax tree, and its imported module's namespace.

    Importing is what turns a spelling into an object, which is the only way to
    ask what a name reaches or what descends from a class. A module that cannot
    be imported fails here as an error rather than a quiet absence.
    """
    for path, tree in _parsed(sources):
        yield path, tree, vars(importlib.import_module(_dotted(path)))


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


def _declared_imports(sources: Iterator[tuple[Path, str]]) -> Iterator[_Import]:
    for path, tree in _parsed(sources):
        yield from _module_imports(path, tree)


def _snapshot_imports() -> list[_Import]:
    return list(_declared_imports(_sources(_SNAPSHOT_SRC)))


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
# Row derivation: the codec answers, holding vocabulary Snapshot never holds.  #
# --------------------------------------------------------------------------- #
# The free row and Change Set helpers the Entity Row Codec replaced. Absent as
# imports AND as definitions, because reintroducing one under Snapshot needs no
# import at all.
DELETED_ROW_HELPERS = frozenset(
    {"full_row", "primary_key_row", "canonical_row", "changed_fields", "effective_change_set"}
)
FORBIDDEN_ROW_IMPORTS = DELETED_ROW_HELPERS | {"BaseModel", "CHANGE_RECORD_SLOT", "WireNames"}

# Pydantic's internal vocabulary, read off the base class rather than listed, so
# `model_dump` and `__pydantic_fields_set__` are forbidden on the same terms as
# `model_fields_set` without anyone having had to think of them; the private
# Change Record slot joins them as the value it actually keys. The two prefixes
# are the boundary of what a spelling can decide: every other name `BaseModel`
# carries is either a name any object has or one of the V1 aliases below.
PRIVATE_VALUE_VOCABULARY = frozenset(
    name for name in dir(BaseModel) if name.startswith(("model_", "__pydantic"))
) | {CHANGE_RECORD_SLOT}


def test_snapshot_holds_none_of_the_codecs_row_vocabulary() -> None:
    # Snapshot asks the Entity Row Codec for a row, and holds no part of what
    # the codec holds: not the Pydantic substrate, not the private Change Record
    # slot, not the exported side table, not a private name out of any
    # `parallax` module, and not a row helper of its own.
    #
    # `self._codec.full_row(...)` IS the codec being consulted, so the guard is
    # stated over what Snapshot imports, defines, and spells rather than over
    # the call.
    #
    # The first four statements are decided by the import inventory and the
    # definition set, both exact. The last is a spelling scan and is the weakest
    # thing in this module: it holds for names that can mean nothing but
    # Pydantic's internals, and the names that would actually derive a row are
    # not among them. `value.dict()`, `value.json()`, and `value.copy()` are V1
    # aliases whose spellings this package already uses for unrelated purposes,
    # so forbidding them would reject working code; a row assembled member by
    # member out of attribute reads has no distinguishing spelling at all.
    #
    # What both leave behind is a row of raw rather than serialized values,
    # which is a property of the statement a write emits and the binds it
    # carries. That is a behavioral question, decided where write behavior is
    # and not by any assertion here.
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
        for path, tree in _parsed(_sources(_SNAPSHOT_SRC))
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in DELETED_ROW_HELPERS
    ] == []
    assert [
        (entry.importer, entry.source) for entry in imported if entry.name == "row_codec_of"
    ] == [("parallax.snapshot.handle._database", _ENTITY_PACKAGE)]
    for spelling in sorted(PRIVATE_VALUE_VOCABULARY):
        assert _hits(_word(spelling), _sources(_SNAPSHOT_SRC)) == [], spelling


def _resolves(namespace: dict[str, object], expression: ast.expr) -> tuple[object, ...]:
    """Every runtime object a name or dotted-name expression denotes.

    Resolution happens in the writing module's own namespace, so an alias, a
    rebinding, or a qualified ``module.Name`` all answer the same object an
    inventory of spellings would have to guess at.
    """
    if isinstance(expression, ast.Tuple):
        return tuple(chain.from_iterable(_resolves(namespace, item) for item in expression.elts))
    if isinstance(expression, ast.Name):
        return (namespace.get(expression.id, getattr(builtins, expression.id, None)),)
    if isinstance(expression, ast.Attribute):
        return tuple(
            getattr(base, expression.attr, None) for base in _resolves(namespace, expression.value)
        )
    return ()


def _caught(
    namespace: dict[str, object], defined: dict[str, ast.ClassDef], expression: ast.expr | None
) -> tuple[object, ...]:
    """The classes an `except` clause's type expression catches, or wider ones.

    A `class` statement in the file under inspection binds a class this run
    created, which is therefore neither an imported class nor an ancestor of
    one; it stands for what it inherits, so a handler naming one declared inside
    a function is judged by its bases rather than left unresolvable. A bare
    `except` names everything.
    """
    if expression is None:
        return (BaseException,)
    if isinstance(expression, ast.Tuple):
        return tuple(
            chain.from_iterable(_caught(namespace, defined, item) for item in expression.elts)
        )
    if isinstance(expression, ast.Name) and expression.id in defined:
        bases = defined[expression.id].bases
        return (
            tuple(chain.from_iterable(_caught(namespace, defined, base) for base in bases))
            if bases
            else (object,)
        )
    return _resolves(namespace, expression)


def _snapshot_handlers() -> Iterator[tuple[str, tuple[object, ...]]]:
    """Every `except` clause under Snapshot, as its site and the classes it catches."""
    for path, tree, namespace in _loaded_modules(_sources(_SNAPSHOT_SRC)):
        defined = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name not in namespace
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                yield _site(path, node.lineno), _caught(namespace, defined, node.type)


def test_no_snapshot_module_catches_the_codecs_own_refusal() -> None:
    # A codec refusal reports first-party misuse, so nothing may catch, wrap, or
    # rethrow one: every keyed-write refusal a developer can provoke is decided
    # from the value's provenance before a row is derived (`m-unit-work`). What
    # the source decides about that is naming, and both halves of naming are
    # here: the refusal type is imported under no spelling, and no handler
    # catches it or any subclass of it.
    #
    # The limit is the handler that catches it without naming it. `except
    # Exception` is legitimate wherever no codec call can reach it — the read
    # path's materialization boundary is one — so rejecting broad handlers
    # rejects working code, and whether a codec call reaches one is a question
    # about paths rather than about spellings. Approximating the reach by
    # matching codec operation NAMES inside a `try` body answers it in neither
    # direction: an unrelated object's `full_row()` is not the codec, and a
    # local alias or one helper call away still is. That no refusal is swallowed
    # is decided by watching one leave a transaction and reach its caller, which
    # is behavioral and belongs with the write verbs.
    #
    # A handler whose type this module cannot resolve to a class is a handler it
    # cannot judge, so those fail here rather than passing quietly.
    assert [
        entry.site for entry in _snapshot_imports() if "EntityRowError" in {entry.name, entry.local}
    ] == []
    handlers = list(_snapshot_handlers())
    assert [
        site
        for site, named in handlers
        if not named or not all(isinstance(caught, type) for caught in named)
    ] == []
    assert [
        site
        for site, named in handlers
        if any(isinstance(caught, type) and issubclass(caught, EntityRowError) for caught in named)
    ] == []


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


# The scopes that declare Entities and form models — the registry-based
# declaration/configuration surface's successors, and the only place a
# `registry` argument would be the removed frontend rather than a collaborator.
# `m-pk-gen`'s `sequence` registry is a real domain object elsewhere in the
# tree; nothing here is a guard against the word.
_DECLARATION_FRONTENDS = (
    _ENTITY_SRC,
    _CORE_SRC / "metamodel",
    _CORE_SRC / "model_formation",
    _PACKAGES / "parallax-descriptor" / "src" / "parallax" / "descriptor",
)


def _registry_arguments() -> list[str]:
    """Every `registry` parameter, class keyword, and keyword argument in them."""
    found: list[str] = []
    for path, tree in _parsed(_sources(*_DECLARATION_FRONTENDS)):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                taken = node.args
                found.extend(
                    _site(path, argument.lineno)
                    for argument in (
                        *taken.posonlyargs,
                        *taken.args,
                        *taken.kwonlyargs,
                        *(one for one in (taken.vararg, taken.kwarg) if one is not None),
                    )
                    if argument.arg == "registry"
                )
            elif isinstance(node, ast.ClassDef | ast.Call):
                found.extend(
                    _site(path, keyword.value.lineno)
                    for keyword in node.keywords
                    if keyword.arg == "registry"
                )
    return sorted(found)


def test_the_removed_registry_argument_stays_absent() -> None:
    # The registry frontend's caller-visible half is a `registry` argument on
    # the declaration surface, which survives every guard stated over the
    # removed type names: a parameter can be reintroduced without naming
    # `EntityRegistry` anywhere. Stated over the declared argument rather than
    # the text `registry=`, because `registry: Registry | None = None` is the
    # same surface returning with no `registry=` anywhere to find.
    assert _registry_arguments() == []


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
    # imports nor lists it. What the package actually publishes is the API
    # snapshot's subject rather than this module's.
    assert _hits(_word(unexported), _sources(_ENTITY_SRC / "__init__.py")) == []


# --------------------------------------------------------------------------- #
# One planner, wired once, decorating nothing.                                #
# --------------------------------------------------------------------------- #
def _assignments(tree: ast.Module) -> list[tuple[list[str], ast.expr]]:
    """Every name-target assignment in a module, annotated ones included."""
    assigned: list[tuple[list[str], ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            assigned.append(
                ([target.id for target in node.targets if isinstance(target, ast.Name)], node.value)
            )
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            assigned.append(
                ([node.target.id] if isinstance(node.target, ast.Name) else [], node.value)
            )
    return assigned


def _reaching_names(tree: ast.Module, namespace: dict[str, object], target: object) -> set[str]:
    """Every name in one module that reaches ``target``, however it was bound.

    Seeded by identity from the module's own namespace — so an import, an ``as``
    clause, a re-export, or a module-level rebinding all answer the same object
    — and closed over the file's assignments, which is what reaches a name bound
    only inside a function.
    """
    reaching = {name for name, value in namespace.items() if value is target}
    assigned = _assignments(tree)
    while True:
        grown = reaching | {
            name
            for names, value in assigned
            if isinstance(value, ast.Name) and value.id in reaching
            for name in names
        }
        if grown == reaching:
            return reaching
        reaching = grown


def _denotes(
    namespace: dict[str, object], expression: ast.expr, reaching: set[str], target: object
) -> bool:
    return (isinstance(expression, ast.Name) and expression.id in reaching) or any(
        denoted is target for denoted in _resolves(namespace, expression)
    )


def _scoped_calls(tree: ast.Module) -> Iterator[tuple[str, ast.Call]]:
    """Every call, paired with the dotted name of the innermost scope holding it."""

    def within(node: ast.AST, scope: tuple[str, ...]) -> Iterator[tuple[str, ast.Call]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                yield from within(child, (*scope, child.name))
                continue
            if isinstance(child, ast.Call):
                yield ".".join(scope), child
            yield from within(child, scope)

    yield from within(tree, ())


def _keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


def _calls_to(target: object) -> Iterator[tuple[Path, str, ast.Call]]:
    """Every first-party call of ``target``, as its file, scope, and call node."""
    for path, tree, namespace in _loaded_modules(_all_sources()):
        reaching = _reaching_names(tree, namespace, target)
        for scope, call in _scoped_calls(tree):
            if _denotes(namespace, call.func, reaching, target):
                yield path, scope, call


def _write_planner_constructions() -> list[tuple[str, str | None]]:
    """Every construction of the Write Planner, as its module and audit argument."""
    return sorted(
        (_dotted(path), _keyword(call, "audit")) for path, _, call in _calls_to(WritePlanner)
    )


def _descendants(root: type) -> Iterator[type]:
    yield root
    for child in root.__subclasses__():
        yield from _descendants(child)


def _write_planner_descendants() -> list[str]:
    """Every first-party class that is, or descends from, the Write Planner.

    Python's own subclass registry answers this once every module is imported,
    so no alias, qualified base spelling, or class name evades it — and a class
    merely named like a planner is not in it.
    """
    for _ in _loaded_modules(_all_sources()):
        pass
    return sorted(
        f"{planner.__module__}.{planner.__qualname__}"
        for planner in _descendants(WritePlanner)
        if planner.__module__.startswith("parallax.")
    )


def _factory_call_sites() -> list[tuple[str, str]]:
    """Every scope that calls the composition-root factory, as module and scope."""
    return sorted({(_dotted(path), scope) for path, scope, _ in _calls_to(build_write_planner)})


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # Lane equivalence is structural rather than parallel wiring: the developer
    # path and the conformance lane call one factory, so a second construction
    # anywhere is a second set of strategies that could drift. Stated over what
    # the callee resolves to rather than over the spelling `WritePlanner(`,
    # because an alias — `_Planner: type[WritePlanner] = WritePlanner` —
    # constructs the same class under a name no text search finds, while an
    # unrelated object's identically named method is not this factory and drops
    # out of the inventory below, taking the entry it stood in for with it. And
    # over the calling scope rather than the calling module, because the factory
    # has to serve every write path, and a module keeps its entry when one of
    # its write paths stops calling.
    #
    # The subclass registry answers one question exactly: no first-party class
    # descends from `WritePlanner`. It is not a proof that no second planner
    # exists, because an independent implementation of the same interface
    # inherits nothing and appears in no registry. What forecloses one is that
    # every write leaves through this factory's planner, which is a property of
    # the write path's behavior rather than of any inventory here.
    assert [module for module, _ in _write_planner_constructions()] == [
        "parallax.snapshot.handle._planning"
    ]
    assert _write_planner_descendants() == ["parallax.core.unit_work.write_planner.WritePlanner"]
    assert _factory_call_sites() == [
        ("parallax.conformance.engine", "_lower_conflict_write"),
        ("parallax.conformance.engine", "_lower_predicate_write_step"),
        ("parallax.conformance.engine", "_lower_resolved"),
        ("parallax.snapshot.handle._database", "Database.__init__"),
    ]


def test_the_write_path_decorates_no_audit_provenance() -> None:
    # Audit decoration is a wired port with nothing behind it. Two statements
    # make that checkable: the write path's one planner is constructed with the
    # neutral strategy, and the neutral strategy returns the step it was handed.
    # Together with the construction inventory above, no planner on any write
    # path holds a strategy that could decorate.
    #
    # Which classes SATISFY the port is deliberately not asked. The port is a
    # runtime-checkable Protocol, so satisfying it means owning a method named
    # `decorate` — the question answers yes for any decorator that has nothing
    # to do with audit, and no for a hand-written stamp under another name.
    #
    # The limit: a value stamped by hand onto a row, under a name of its own and
    # ahead of the reserved audit property names, satisfies no port and matches
    # no vocabulary nameable here. What a write emits is a property of the
    # statement and its binds, decided where write behavior is.
    assert _write_planner_constructions() == [("parallax.snapshot.handle._planning", "NO_AUDIT")]
    step = cast("PlannedWrite", object())
    assert (
        NO_AUDIT.decorate(
            step,
            subject_identity=cast("SubjectIdentity", "unattributed"),
            transaction_instant=cast("TransactionInstant", None),
        )
        is step
    )
