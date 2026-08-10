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
with the kind of evidence that bears on it — which is behavioral, and lives with
the behavior rather than here. Behavior narrows these rather than closing them:
an emitted statement carries a row's content and not its provenance, and a
handler is witnessed on the path a test drives and not on the others.
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
    ("parallax.snapshot.materialize._neutral", "_graph_input"): frozenset({"ValueObjectRecord"}),
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
# The conformance adapter's reaches into shipped-distribution privates.        #
# --------------------------------------------------------------------------- #
# The adapter drives production through supported entry points; what remains
# below is the residue that has no supported entry point to drive, and each
# entry is a `python.md` §7 decision rather than an import someone wrote.
#
# Two families, for two reasons:
#
# - The DESCRIPTOR RECORD GRAPH. A corpus model is a descriptor document and a
#   case reads it as a parsed record graph — an Entity's authored inheritance
#   role, a family's participants, an Attribute's declared name — for documents
#   that have not formed and, for the four `rejected` inline models, never will.
#   `m-descriptor`'s complete public surface answers with a Domain Model Hub or
#   a refusal, neither of which is a readable descriptor, so the records are the
#   only answer. Making them public is a permanent `parallax-descriptor` API
#   decision this ticket did not take.
# - The ENTITY FRONTEND seams `AnotherSource` composes. Both are already accepted
#   private seams of production's own (`ACCEPTED_PRIVATE_ENTITY_REACHES` above
#   names `model_of` for the composition root and `lower_find_query` for the read
#   preflight); a third, development-only consumer of the same two seams is not a
#   reason to widen `parallax.core.entity`'s shipped surface.
#
# Keyed by REACHING module for the same reason the snapshot inventory is: a
# second module importing an already-accepted name is a new reach.
ACCEPTED_CONFORMANCE_PRIVATE_REACHES: dict[tuple[str, str], frozenset[str]] = {
    ("parallax.conformance.another_source", "parallax.core.entity._model"): frozenset({"model_of"}),
    ("parallax.conformance.another_source", "parallax.core.entity._query"): frozenset(
        {"lower_find_query"}
    ),
    ("parallax.conformance.engine", "parallax.descriptor._family"): frozenset({"family_of"}),
    ("parallax.conformance.engine", "parallax.descriptor._records"): frozenset(
        {"Attribute", "Entity", "Metamodel", "declaring_entity"}
    ),
    ("parallax.conformance.engine", "parallax.descriptor._serde"): frozenset({"deserialize"}),
    ("parallax.conformance.models", "parallax.core._formation_profile"): frozenset(
        {"form_metamodel"}
    ),
    ("parallax.conformance.models", "parallax.descriptor._adapter"): frozenset(
        {"unresolved_metamodel"}
    ),
    ("parallax.conformance.models", "parallax.descriptor._ingest"): frozenset({"ingest_document"}),
    ("parallax.conformance.models", "parallax.descriptor._records"): frozenset({"Metamodel"}),
    ("parallax.conformance.provision", "parallax.descriptor._records"): frozenset({"Metamodel"}),
}

_CONFORMANCE_SRC = _PACKAGES / "parallax-conformance" / "src" / "parallax" / "conformance"


def _conformance_private_reaches() -> dict[tuple[str, str], set[str]]:
    """Every name the conformance package imports from an underscored module of a
    SHIPPED distribution, keyed by ``(importer, imported module)``.

    A module counts as private when any dotted segment after the distribution's
    top package starts with an underscore, so both
    ``parallax.core.entity._query`` and a future ``parallax.core._x.y`` are seen.
    """
    reached: dict[tuple[str, str], set[str]] = {}
    for imported in _declared_imports(_sources(_CONFORMANCE_SRC)):
        source = imported.source or imported.name
        if not source.startswith("parallax.") or source.startswith("parallax.conformance"):
            continue
        if not any(part.startswith("_") for part in source.split(".")[1:]):
            continue
        reached.setdefault((imported.importer, source), set()).add(imported.name)
    return reached


def test_conformance_private_production_reaches_are_exactly_the_accepted_seams() -> None:
    assert _conformance_private_reaches() == {
        reach: set(names) for reach, names in ACCEPTED_CONFORMANCE_PRIVATE_REACHES.items()
    }


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
    # carries. That is a behavioral question, answered where write behavior is
    # and not by any assertion here — and answered about the row's content, not
    # about where the row came from: a row assembled anywhere else that
    # serializes identically emits the same statement and the same binds.
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


# --------------------------------------------------------------------------- #
# What a spelling denotes where it is written.                                #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _Imported:
    """What an import binds, imported when a guard asks what its name denotes.

    Deferred rather than resolved where the statement is read, because a
    function-local import is often the one its module could not make at import
    time; one that cannot be made denotes nothing, rather than failing a guard
    that never asked about it.
    """

    package: str
    """What a relative import counts from: the importing module's package."""
    source: str
    """The dotted module the statement imports, leading dots included."""
    attribute: str
    """The name taken out of it; empty when the local name is bound to a module."""

    def denotes(self) -> tuple[object, ...]:
        try:
            module = importlib.import_module(self.source, self.package or None)
        except ImportError:
            return ()
        if not self.attribute:
            return (module,)
        if hasattr(module, self.attribute):
            return (getattr(module, self.attribute),)
        try:
            return (importlib.import_module(f".{self.attribute}", module.__name__),)
        except ImportError:
            return (None,)


@dataclass(frozen=True, slots=True)
class _Denoted:
    """Objects a binding takes from a scope other than the one it binds in."""

    objects: tuple[object, ...]


_Bound = ast.expr | _Imported | _Denoted | None
"""One value a name takes: an expression, an import, objects, or nothing decidable."""

_BEFORE_THE_BODY = (0, 0)
"""Where a parameter binds: ahead of every statement its scope writes."""


@dataclass(frozen=True, slots=True)
class _Binding:
    """One value a name takes, and the point in its scope that gives it.

    ``statement`` carries a position only when the binding is one of the
    scope's own unconditional statements, which is what lets source order
    decide: the last such binding before a use is the only one that reaches it.
    A binding made under an `if`, inside a loop body, in a `try`, or by a
    handler target carries none, because which one a use sees is a question
    about control flow rather than about source order — so all of them stay in
    play and the scope answers with everything the name MAY denote.
    """

    value: _Bound
    statement: tuple[int, int] | None


@dataclass(frozen=True, eq=False, slots=True)
class _Scope:
    """The names a lexical scope binds, and where a name it does not bind resolves.

    A module's names come from the imported module's namespace, which is exact:
    it holds every module-level import, definition, and rebinding as the object
    it ended up being. Only the scopes written inside one are reconstructed, out
    of the statements that bind — imports, assignments, parameters and their
    defaults, and loop, `with`, and handler targets. A scope shadows the scope
    enclosing it for every name it binds, so a name bound to something no
    reading of the source evaluates denotes an unknown object rather than
    falling through to a module-level name that happens to share its spelling.
    An unknown is a value like any other, so it stays in the answer and keeps
    a guard from reading certainty into a name it cannot follow.
    """

    namespace: dict[str, object]
    bound: dict[str, tuple[_Binding, ...]]
    parent: _Scope | None
    class_body: bool = False

    def binding(self, name: str) -> _Scope | None:
        """The nearest scope binding ``name``, or `None` when the module holds it."""
        if name in self.bound:
            return self
        return self.parent.binding(name) if self.parent is not None else None


def _reaching(bindings: tuple[_Binding, ...], use: tuple[int, int]) -> tuple[_Binding, ...]:
    """The bindings a use written in the binding scope itself can see.

    Straight-line rebinding is decided by source order alone: when every
    binding of the name is one of the scope's own statements, the last one
    before the use is what the name holds there, and the ones it overwrote are
    dead. Everything else keeps the whole set, so control flow never silently
    narrows an answer. A use in a scope nested inside the binding one never
    reaches here: it runs when its own scope is called rather than where it is
    written, so every binding stays in play for it.
    """
    positioned = {
        binding.statement: binding for binding in bindings if binding.statement is not None
    }
    if len(positioned) != len(bindings):
        return bindings
    before = sorted(position for position in positioned if position < use)
    return (positioned[before[-1]],) if before else bindings


def _resolves(
    scope: _Scope, expression: ast.expr, seen: frozenset[tuple[int, str]] = frozenset()
) -> tuple[object, ...]:
    """Every runtime object an expression MAY denote where it is written.

    Resolution runs in the scope holding the expression and outward through the
    scopes enclosing it, so an alias, a rebinding, a parameter default, a
    function-local import, a destructured target, and a qualified
    ``module.Name`` all answer the same object an inventory of spellings would
    have to guess at.

    The answer is a set because a name under control flow holds one of several
    values, and it is the set of everything reachable rather than a guess at
    one of them. A guard therefore has two questions to choose between — whether
    the target is IN the answer, and whether it is ALL of it — and the choice is
    what keeps the guard sound in the direction it needs.
    """
    if isinstance(expression, ast.Tuple):
        return tuple(chain.from_iterable(_resolves(scope, item, seen) for item in expression.elts))
    if isinstance(expression, ast.Attribute):
        return tuple(
            getattr(base, expression.attr, None)
            for base in _resolves(scope, expression.value, seen)
        )
    if not isinstance(expression, ast.Name):
        return ()
    holder = scope.binding(expression.id)
    if holder is None:
        return (scope.namespace.get(expression.id, getattr(builtins, expression.id, None)),)
    mark = (id(holder), expression.id)
    if mark in seen:
        return ()
    bindings = holder.bound[expression.id]
    if holder is scope:
        bindings = _reaching(bindings, (expression.lineno, expression.col_offset))
    return tuple(
        chain.from_iterable(_denoted(holder, binding.value, seen | {mark}) for binding in bindings)
    )


def _denoted(scope: _Scope, bound: _Bound, seen: frozenset[tuple[int, str]]) -> tuple[object, ...]:
    if bound is None:
        return (None,)
    if isinstance(bound, _Imported):
        return bound.denotes()
    if isinstance(bound, _Denoted):
        return bound.objects
    return _resolves(scope, bound, seen)


_NESTED_SCOPE = (
    ast.FunctionDef
    | ast.AsyncFunctionDef
    | ast.ClassDef
    | ast.Lambda
    | ast.ListComp
    | ast.SetComp
    | ast.DictComp
    | ast.GeneratorExp
)

_ANONYMOUS_SCOPE = {
    ast.Lambda: "<lambda>",
    ast.ListComp: "<listcomp>",
    ast.SetComp: "<setcomp>",
    ast.DictComp: "<dictcomp>",
    ast.GeneratorExp: "<genexpr>",
}
"""What Python calls the scopes that have no declared name, as it qualifies them."""


def _own_nodes(node: ast.AST) -> Iterator[tuple[ast.AST, tuple[int, int] | None]]:
    """Every node the scope headed by ``node`` holds itself, nested scopes aside.

    Each carries its position when it is one of the scope's own statements, and
    `None` when something between it and the scope decides whether it runs.
    """
    body = (
        node.body
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
        else []
    )
    statements = {id(one): (one.lineno, one.col_offset) for one in body}

    def within(parent: ast.AST) -> Iterator[tuple[ast.AST, tuple[int, int] | None]]:
        for child in ast.iter_child_nodes(parent):
            yield child, statements.get(id(child))
            if not isinstance(child, _NESTED_SCOPE):
                yield from within(child)

    yield from within(node)


def _bound_by(target: ast.expr, value: ast.expr | None) -> Iterator[tuple[str, ast.expr | None]]:
    """Each name an assignment target binds, and what the assignment gives it.

    A tuple target takes its elements from a tuple value of the same length,
    which is what makes ``planner, _ = WritePlanner, None`` a binding rather
    than an unknown.
    """
    if isinstance(target, ast.Name):
        yield target.id, value
    elif isinstance(target, ast.Starred):
        yield from _bound_by(target.value, None)
    elif isinstance(target, ast.Tuple | ast.List):
        elements = value.elts if isinstance(value, ast.Tuple | ast.List) else []
        aligned = len(elements) == len(target.elts) and not any(
            isinstance(element, ast.Starred) for element in target.elts
        )
        for index, element in enumerate(target.elts):
            yield from _bound_by(element, elements[index] if aligned else None)


def _imports_bound(
    node: ast.Import | ast.ImportFrom, package: str
) -> Iterator[tuple[str, _Imported]]:
    """Each local name an import statement binds, and what it binds it to."""
    if isinstance(node, ast.ImportFrom):
        source = "." * node.level + (node.module or "")
        for alias in node.names:
            yield alias.asname or alias.name, _Imported(package, source, alias.name)
        return
    for alias in node.names:
        root = alias.name.partition(".")[0]
        yield (
            (alias.asname, _Imported(package, alias.name, ""))
            if alias.asname
            else (root, _Imported(package, root, ""))
        )


def _parameter_bindings(taken: ast.arguments, writing: _Scope) -> Iterator[tuple[str, _Bound]]:
    """Each parameter, bound to its default — which the scope writing the `def` evaluates."""
    positional = [*taken.posonlyargs, *taken.args]
    defaults: list[ast.expr | None] = [
        *([None] * (len(positional) - len(taken.defaults))),
        *taken.defaults,
    ]
    for argument, default in (
        *zip(positional, defaults, strict=True),
        *zip(taken.kwonlyargs, taken.kw_defaults, strict=True),
    ):
        yield argument.arg, _Denoted(_resolves(writing, default)) if default else None
    for argument in (taken.vararg, taken.kwarg):
        if argument is not None:
            yield argument.arg, None


def _bindings(node: ast.AST, package: str, writing: _Scope) -> dict[str, tuple[_Binding, ...]]:
    """Every name a scope binds, each to every value its own statements give it."""
    bound: dict[str, list[_Binding]] = {}

    def bind(name: str, value: _Bound, statement: tuple[int, int] | None) -> None:
        bound.setdefault(name, []).append(_Binding(value, statement))

    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
        for name, value in _parameter_bindings(node.args, writing):
            bind(name, value, _BEFORE_THE_BODY)
    for child, statement in _own_nodes(node):
        if isinstance(child, ast.Import | ast.ImportFrom):
            for name, imported in _imports_bound(child, package):
                bind(name, imported, statement)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                for name, value in _bound_by(target, child.value):
                    bind(name, value, statement)
        elif isinstance(child, ast.AnnAssign | ast.NamedExpr):
            for name, value in _bound_by(child.target, child.value):
                bind(name, value, statement)
        elif isinstance(child, ast.AugAssign):
            for name, _ in _bound_by(child.target, None):
                bind(name, None, statement)
        elif isinstance(child, ast.For | ast.AsyncFor | ast.comprehension):
            for name, _ in _bound_by(child.target, None):
                bind(name, None, None)
        elif isinstance(child, ast.withitem) and child.optional_vars is not None:
            for name, _ in _bound_by(child.optional_vars, None):
                bind(name, None, None)
        elif (
            isinstance(
                child, ast.ExceptHandler | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
            )
            and child.name is not None
        ):
            bind(child.name, None, statement)
    return {name: tuple(values) for name, values in bound.items()}


def _nested_scope(node: ast.AST, parent: _Scope, package: str) -> _Scope:
    """The scope ``node`` heads, written inside ``parent``.

    A function or comprehension written in a class body resolves its own names
    past that body, as Python does. Its parameter defaults do not: they are
    evaluated where the `def` statement stands, so `class C: P = Planner; def
    f(make=P)` takes `P` from the class body the same reading of the source
    that denies the body to `f`.
    """
    class_body = isinstance(node, ast.ClassDef)
    enclosing = parent
    while not class_body and enclosing.class_body and enclosing.parent is not None:
        enclosing = enclosing.parent
    return _Scope(parent.namespace, _bindings(node, package, parent), enclosing, class_body)


def _in_scopes(
    tree: ast.Module, namespace: dict[str, object]
) -> Iterator[tuple[str, _Scope, ast.AST]]:
    """Every node in a module, with the dotted name and the bindings of its scope."""
    package = str(namespace.get("__package__") or "")

    def within(
        node: ast.AST, name: tuple[str, ...], scope: _Scope
    ) -> Iterator[tuple[str, _Scope, ast.AST]]:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, _NESTED_SCOPE):
                declared = (
                    child.name
                    if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                    else _ANONYMOUS_SCOPE[type(child)]
                )
                yield from within(child, (*name, declared), _nested_scope(child, scope, package))
                continue
            yield ".".join(name), scope, child
            yield from within(child, name, scope)

    yield from within(tree, (), _Scope(namespace, {}, None))


def _caught(
    scope: _Scope, defined: dict[str, ast.ClassDef], expression: ast.expr | None
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
        return tuple(chain.from_iterable(_caught(scope, defined, item) for item in expression.elts))
    if isinstance(expression, ast.Name) and expression.id in defined:
        bases = defined[expression.id].bases
        return (
            tuple(chain.from_iterable(_caught(scope, defined, base) for base in bases))
            if bases
            else (object,)
        )
    return _resolves(scope, expression)


def _snapshot_handlers() -> Iterator[tuple[str, tuple[object, ...]]]:
    """Every `except` clause under Snapshot, as its site and the classes it catches."""
    for path, tree, namespace in _loaded_modules(_sources(_SNAPSHOT_SRC)):
        defined = {
            node.name: node
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef) and node.name not in namespace
        }
        for _, scope, node in _in_scopes(tree, namespace):
            if isinstance(node, ast.ExceptHandler):
                yield _site(path, node.lineno), _caught(scope, defined, node.type)


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
    # local alias or one helper call away still is. That a refusal is not
    # swallowed is shown by watching one leave a transaction and reach its
    # caller, which is behavioral and belongs with the write verbs — and shows
    # it for the codec operation and the write path that raised it, since a
    # handler around one write path says nothing about another.
    #
    # A handler is judged over every class its type MAY be, so one whose type a
    # branch chooses catches a refusal here if any branch does. A handler whose
    # type this module cannot resolve to a class is a handler it cannot judge,
    # so those fail here rather than passing quietly.
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
    # imports nor lists it.
    assert _hits(_word(unexported), _sources(_ENTITY_SRC / "__init__.py")) == []


# --------------------------------------------------------------------------- #
# One planner, wired once, decorating nothing.                                #
# --------------------------------------------------------------------------- #
def _keyword(call: ast.Call, name: str) -> str | None:
    for keyword in call.keywords:
        if keyword.arg == name:
            return ast.unparse(keyword.value)
    return None


@dataclass(frozen=True, slots=True)
class _CallSite:
    """A first-party call, and every object its callee may denote where it stands.

    The two questions an inventory can ask of that set point in opposite
    directions, and each guard below takes the one that makes it fail rather
    than pass when the source stops deciding.
    """

    module: str
    scope: str
    call: ast.Call
    denoted: tuple[object, ...]

    def may_reach(self, target: object) -> bool:
        """Some binding reaching the callee is ``target``, so the call may be one."""
        return any(denoted is target for denoted in self.denoted)

    def only_reaches(self, target: object) -> bool:
        """Every binding reaching the callee is ``target``, so the call is one."""
        return bool(self.denoted) and all(denoted is target for denoted in self.denoted)


def _call_sites() -> Iterator[_CallSite]:
    """Every first-party call, with its module, its scope, and what its callee denotes."""
    for path, tree, namespace in _loaded_modules(_all_sources()):
        for name, scope, node in _in_scopes(tree, namespace):
            if isinstance(node, ast.Call):
                yield _CallSite(_dotted(path), name, node, _resolves(scope, node.func))


def _write_planner_constructions() -> list[tuple[str, str | None]]:
    """Every construction of the Write Planner, as its module and audit argument."""
    return sorted(
        (site.module, _keyword(site.call, "audit"))
        for site in _call_sites()
        if site.may_reach(WritePlanner)
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
    """Every scope whose call reaches the composition-root factory and nothing else."""
    return sorted(
        {
            (site.module, site.scope)
            for site in _call_sites()
            if site.only_reaches(build_write_planner)
        }
    )


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # Lane equivalence is structural rather than parallel wiring: the developer
    # path and the conformance lane call one factory, so a second construction
    # anywhere is a second set of strategies that could drift. Stated over what
    # the callee resolves to rather than over the spelling `WritePlanner(`,
    # because an alias — `_Planner: type[WritePlanner] = WritePlanner`, a
    # function-local `import ... as`, a destructured target, a parameter default
    # — constructs the same class under a name no text search finds, while an
    # unrelated object's identically named method is not this factory and drops
    # out of the inventory below, taking the entry it stood in for with it. And
    # over the calling scope rather than the calling module, because the factory
    # has to serve every write path, and a module keeps its entry when one of
    # its write paths stops calling.
    #
    # The two inventories ask opposite questions of one resolution, each the
    # question that fails rather than passes where the source stops deciding. A
    # construction is counted wherever the callee MAY be `WritePlanner`, so a
    # planner built under a name a branch chooses is still counted. A factory
    # call site is counted only where the callee can be NOTHING BUT the factory,
    # so a scope keeps its entry only while its call still reaches the
    # composition root under every binding: rebinding the name, straight-line or
    # behind a branch, drops the entry and fails this assertion instead of
    # inheriting it.
    #
    # What binds a name is lexical and decided here, source order included — a
    # scope's own straight-line statements rebind, so the last one before a call
    # is what the call reaches and what it overwrote is dead. What a caller
    # passes into a parameter is not: a class handed to a helper and constructed
    # there is constructed under a name this module resolves to nothing, and
    # following it would mean tracing values across call boundaries rather than
    # reading scopes. The inventory is of names, and says nothing about that.
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
    # statement and its binds, constrained where write behavior is — an extra
    # column or an extra bind fails an exact-statement assertion for the write
    # shapes those assertions cover, and a stamp that never varies survives
    # every comparison of two writes to each other.
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
