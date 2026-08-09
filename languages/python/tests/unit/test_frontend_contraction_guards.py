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

Each guard is scoped to the prohibited thing itself — a type and its
descendants, a protocol's implementations, one named surface, one code path —
rather than to a name shape or an inventory of accepted spellings. Scoping that
way makes a guard stronger and narrower at once: it catches a reconstruction
spelled differently from the one that prompted it, and it stays silent for
unrelated code that merely shares a spelling. Several guards therefore import
the distributions and ask Python, because subclassing and protocol satisfaction
are runtime facts that source text only approximates.

Two limits are stated rather than guarded, so no assertion here is read as
covering them: a row assembled member by member out of ordinary attribute
reads, and an audit value stamped by hand under a name of its own. Each is
named again at the guard whose subject it borders, with what does grade it.
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
from parallax.core.entity import EntityRowCodec, EntityRowError
from parallax.core.entity._entity import CHANGE_RECORD_SLOT
from parallax.core.unit_work import (
    NO_AUDIT,
    AuditStrategy,
    PlannedWrite,
    SubjectIdentity,
    TransactionInstant,
    WritePlanner,
)

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


def _imported(
    sources: Iterator[tuple[Path, str]],
) -> Iterator[tuple[Path, ast.Module, dict[str, object]]]:
    """Each source file, its syntax tree, and its imported module's namespace.

    `test_smoke.py` proves every module here imports cleanly, so the guards that
    need a runtime answer — what a name resolves to, what descends from a class,
    what satisfies a protocol — can ask for one.
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


def _imports(sources: Iterator[tuple[Path, str]]) -> Iterator[_Import]:
    for path, tree in _parsed(sources):
        yield from _module_imports(path, tree)


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
# Row derivation: the codec answers, holding vocabulary Snapshot never holds.  #
# --------------------------------------------------------------------------- #
# The free row and Change Set helpers the Entity Row Codec replaced. Absent as
# imports AND as definitions, because reintroducing one under Snapshot needs no
# import at all.
DELETED_ROW_HELPERS = frozenset(
    {"full_row", "primary_key_row", "canonical_row", "changed_fields", "effective_change_set"}
)
FORBIDDEN_ROW_IMPORTS = DELETED_ROW_HELPERS | {"BaseModel", "CHANGE_RECORD_SLOT", "WireNames"}

# Pydantic's value-reading API, read off the base class rather than listed, so
# `model_dump` and `__pydantic_fields_set__` are forbidden on the same terms as
# `model_fields_set` without anyone having had to think of them; the private
# Change Record slot joins them as the value it actually keys.
PRIVATE_VALUE_VOCABULARY = frozenset(
    name for name in dir(BaseModel) if name.startswith(("model_", "__pydantic"))
) | {CHANGE_RECORD_SLOT}


def test_snapshot_holds_none_of_the_codecs_row_vocabulary() -> None:
    # Snapshot asks the Entity Row Codec for a row, and holds no part of what
    # the codec holds: not the Pydantic substrate, not the private Change Record
    # slot, not the exported side table, not a private name out of any
    # `parallax` module, and not a row helper of its own. The codec's own
    # audit-neutrality proof (`test_row_codec.py`) is what makes consulting it
    # enough.
    #
    # `self._codec.full_row(...)` IS the codec being consulted, so the guard is
    # stated over what Snapshot imports, defines, and reads rather than over the
    # call.
    #
    # The limit: a row assembled member by member out of ordinary attribute
    # reads touches none of this vocabulary and is indistinguishable at the
    # source from any other attribute read. Such a row would carry raw rather
    # than serialized values, which the write path's golden SQL grades; no
    # source-shape assertion can see it, and none below claims to.
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


# The codec's own operation surface, read off the class, so an operation added
# to it inherits the guard below rather than needing to be added to a list.
CODEC_OPERATIONS = frozenset(name for name in vars(EntityRowCodec) if not name.startswith("_"))


def _named_types(namespace: dict[str, object], expression: ast.expr) -> tuple[object, ...]:
    """Every runtime object an `except` clause's type expression names."""
    if isinstance(expression, ast.Tuple):
        return tuple(chain.from_iterable(_named_types(namespace, item) for item in expression.elts))
    if isinstance(expression, ast.Name):
        return (namespace.get(expression.id, getattr(builtins, expression.id, None)),)
    if isinstance(expression, ast.Attribute):
        return tuple(
            getattr(base, expression.attr, None)
            for base in _named_types(namespace, expression.value)
        )
    return ()


def _snapshot_handlers() -> Iterator[tuple[str, tuple[object, ...]]]:
    """Every `except` clause under Snapshot, as its site and the types it names.

    Resolved in the writing module's own namespace, so an alias, a rebinding, or
    a qualified `module.Name` all answer the same class an inventory of
    spellings would have to guess at. A bare `except` names everything.
    """
    for path, tree, namespace in _imported(_sources(_SNAPSHOT_SRC)):
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                named = (
                    (BaseException,) if node.type is None else _named_types(namespace, node.type)
                )
                yield _site(path, node.lineno), named


def _codec_calls_inside_try() -> list[str]:
    """Every codec operation called from inside a `try` body under Snapshot."""
    return [
        _site(path, node.lineno)
        for path, tree in _parsed(_sources(_SNAPSHOT_SRC))
        for statement in ast.walk(tree)
        if isinstance(statement, ast.Try | ast.TryStar)
        for guarded in statement.body
        for node in ast.walk(guarded)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr in CODEC_OPERATIONS)
            or (isinstance(node.func, ast.Name) and node.func.id in CODEC_OPERATIONS)
        )
    ]


def test_no_snapshot_module_catches_the_codecs_own_refusal() -> None:
    # A codec refusal reports first-party misuse, so nothing may catch, wrap, or
    # rethrow one: every keyed-write refusal a developer can provoke is decided
    # from the value's provenance before a row is derived (`m-unit-work`). Two
    # statements pin that without freezing Snapshot's unrelated exception
    # boundaries — no handler names the refusal, and no codec operation is
    # called from inside a `try` body, so no handler however broadly typed
    # stands between a codec call and its caller. That no refusal reaches an
    # application is graded where the verbs' own steering is,
    # `test_transaction_writes.py`.
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
    assert _codec_calls_inside_try() == []


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


def _is_call_to(call: ast.Call, callees: set[str], attribute: str) -> bool:
    func = call.func
    return (isinstance(func, ast.Name) and func.id in callees) or (
        isinstance(func, ast.Attribute) and func.attr == attribute
    )


def _calls(tree: ast.Module, callees: set[str], attribute: str) -> Iterator[ast.Call]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _is_call_to(node, callees, attribute):
            yield node


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


def _write_planner_constructions() -> list[tuple[str, str | None]]:
    """Every construction of the Write Planner, as its module and audit argument."""
    return sorted(
        (_dotted(path), _keyword(call, "audit"))
        for path, tree in _parsed(_all_sources())
        for call in _calls(
            tree, _bound_to(tree, "parallax.core.unit_work", "WritePlanner"), "WritePlanner"
        )
    )


def _descendants(root: type) -> Iterator[type]:
    yield root
    for child in root.__subclasses__():
        yield from _descendants(child)


def _write_planner_hierarchy() -> list[str]:
    """Every first-party class that is, or descends from, the Write Planner.

    Python's own subclass registry answers this once every module is imported,
    so no alias, qualified base spelling, or class name evades it — and a class
    merely named like a planner is not in it.
    """
    for _ in _imported(_all_sources()):
        pass
    return sorted(
        f"{planner.__module__}.{planner.__qualname__}"
        for planner in _descendants(WritePlanner)
        if planner.__module__.startswith("parallax.")
    )


def _factory_call_sites() -> list[tuple[str, str]]:
    """Every scope that calls the composition-root factory, as module and scope."""
    return sorted(
        {
            (_dotted(path), scope)
            for path, tree in _parsed(_all_sources())
            for scope, call in _scoped_calls(tree)
            if _is_call_to(
                call,
                _bound_to(tree, "parallax.snapshot.handle", "build_write_planner"),
                "build_write_planner",
            )
        }
    )


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # Lane equivalence is structural rather than parallel wiring: the developer
    # path and the conformance lane call one factory, so a second construction
    # anywhere is a second set of strategies that could drift. Stated over the
    # resolved callee rather than the spelling `WritePlanner(`, because a local
    # alias constructs the same class under a name no text search finds; and
    # over the calling scope rather than the calling module, because the factory
    # has to serve every write path, and a module keeps its entry when one of
    # its write paths stops calling.
    assert [module for module, _ in _write_planner_constructions()] == [
        "parallax.snapshot.handle._planning"
    ]
    assert _write_planner_hierarchy() == ["parallax.core.unit_work.write_planner.WritePlanner"]
    assert _factory_call_sites() == [
        ("parallax.conformance.engine", "_lower_conflict_write"),
        ("parallax.conformance.engine", "_lower_predicate_write_step"),
        ("parallax.conformance.engine", "_lower_resolved"),
        ("parallax.snapshot.handle._database", "Database.__init__"),
    ]


def _snapshot_classes() -> Iterator[type]:
    """Every class Snapshot's own modules define."""
    for _, _, namespace in _imported(_sources(_SNAPSHOT_SRC)):
        module = namespace["__name__"]
        for value in namespace.values():
            if isinstance(value, type) and value.__module__ == module:
                yield value


def test_the_write_path_decorates_no_audit_provenance() -> None:
    # Audit decoration is a wired port with nothing behind it. Three statements
    # make "no write path emits an audit value" checkable: the write path's one
    # planner is built with the neutral strategy, no class under Snapshot
    # satisfies the decoration port, and the neutral strategy returns the step it
    # was handed. Scoped to the port and to that construction, so an `audit=`
    # option somewhere off the write path and an ordinary decoration helper that
    # implements nothing are none of this guard's business.
    #
    # The limit: a value stamped by hand onto a row, under a name of its own and
    # ahead of the reserved audit property names, satisfies no port and matches
    # no vocabulary nameable here. What a write actually emits is graded by the
    # write tests' golden SQL.
    assert _write_planner_constructions() == [("parallax.snapshot.handle._planning", "NO_AUDIT")]
    assert [
        f"{implementation.__module__}.{implementation.__qualname__}"
        for implementation in _snapshot_classes()
        if issubclass(implementation, AuditStrategy)
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
