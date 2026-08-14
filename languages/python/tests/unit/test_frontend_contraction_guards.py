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

Every guard is stated over something the source decides outright: what a module
imports, what it defines, what a scope declares as a parameter, whether a file
exists, whether a spelling occurs. One guard instead imports every distribution
and asks Python, because a class's ancestry is a runtime fact that source text
only approximates. The exact-set form is what makes any of them useful: a guard
names the site of whatever is new rather than reporting that a count moved.

A guard stated over a spelling alone is the weaker kind, because an alias evades
it. Each such guard says so where it stands and names the behavioral evidence
that covers what it admits, rather than leaving a reader to infer coverage it
does not have.

Three prohibitions this contraction also carries are not decidable from the
source at all, and nothing here is to be read as covering them:

- a row derived from something other than the codec — assembled member by member
  out of ordinary attribute reads, or through Pydantic's V1 aliases, whose
  spellings (``dict``, ``json``, ``copy``, ``schema``, ``validate``,
  ``construct``) are ordinary Python words this package already uses for
  unrelated purposes;
- a handler typed broadly enough to catch a codec refusal without naming it,
  which is prohibited only where a codec call can actually reach it. No guard
  here borders this one. The ordering it derives from — `spec/python.md` §5
  decides a keyed verb's refusal in the shared preamble, ahead of any row
  derivation, so the refusal a caller observes carries no codec failure as its
  cause — is graded at the boundary instead, by the compatibility cases
  ``m-unit-work-017-update-of-a-value-no-managed-read-produced`` and
  ``m-unit-work-019-write-of-a-value-another-source-produced``, and by
  `tests/unit/test_write_value_runner.py` and
  `tests/unit/test_transaction_writes.py`;
- an audit value stamped by hand under a name of its own.

Each asks what a value IS, or what a call at runtime REACHES, rather than how
the source spells it, and each is named again with the evidence that bears on
it — behavioral evidence, which lives with the behavior rather than here. The
first is named at the guard whose subject it borders, the second at the modules
just named, and the third in `tests/unit/test_planner_composition.py`, where the
audit strategy the composition root wires is graded. Behavior narrows these
rather than closing them: an emitted statement carries a row's content and not
its provenance, and a handler is witnessed on the path a test drives and not on
the others.
"""

from __future__ import annotations

import ast
import importlib
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from pydantic import BaseModel

from _support.distributions import ALL_PACKAGES, PRODUCTION_PACKAGES, TOP_PACKAGE_DIR
from _support.repo import PY_ROOT
from parallax.core.entity._entity import CHANGE_RECORD_SLOT
from parallax.core.unit_work import WritePlanner

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


def _import_every_module(sources: Iterator[tuple[Path, str]]) -> None:
    """Import each source file, so a guard can ask Python rather than the text.

    Importing is what turns a spelling into an object, which is the only way to
    ask what descends from a class. A module that cannot be imported fails here
    as an error rather than a quiet absence.
    """
    for path, _text in sources:
        importlib.import_module(_dotted(path))


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
    ("parallax.snapshot.materialize._wire", "_graph_input"): frozenset({"ValueObjectRecord"}),
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
# Two reasons, both `python.md` §7 decisions. `model_of` is an accepted private
# seam of production's own (`ACCEPTED_PRIVATE_ENTITY_REACHES` above names it for
# the composition root), and its own contract calls it a first-party runtime seam
# rather than developer surface — it exists so a separately distributed frontend
# can read the accepted model out of a Domain Model, which is exactly what these
# two modules do. `parallax.core.object_query._fluent` is the typed Object Query
# surface, deliberately absent from its own package interface so no execution
# module can reach the Entity frontend through it; a caller that WANTS the typed
# surface names the module, exactly as the snapshot handle does.
#
# The descriptor record graph is NOT here: the adapter composes corpus models
# through the public `domain_model_from_*` doors and reads the accepted model's
# own vocabulary, so no `parallax.descriptor` private module is reached at all.
#
# Keyed by REACHING module for the same reason the snapshot inventory is: a
# second module importing an already-accepted name is a new reach — which is why
# `model_of` appears twice rather than once.
ACCEPTED_CONFORMANCE_PRIVATE_REACHES: dict[tuple[str, str], frozenset[str]] = {
    ("parallax.conformance.another_source", "parallax.core.entity._model"): frozenset({"model_of"}),
    ("parallax.conformance.another_source", "parallax.core.object_query._fluent"): frozenset(
        {"ObjectQuery", "object_query_node"}
    ),
    ("parallax.conformance.models", "parallax.core.entity._model"): frozenset({"model_of"}),
}

_CONFORMANCE_SRC = _PACKAGES / "parallax-conformance" / "src" / "parallax" / "conformance"


def _conformance_private_reaches() -> dict[tuple[str, str], set[str]]:
    """Every name the conformance package imports from an underscored module of a
    SHIPPED distribution, keyed by ``(importer, imported module)``.

    A module counts as private when any dotted segment after the distribution's
    top package starts with an underscore, so both
    ``parallax.core.object_query._fluent`` and a future ``parallax.core._x.y``
    are seen.
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
# One planner class, constructed in one module.                               #
# --------------------------------------------------------------------------- #
def _write_planner_construction_files() -> set[str]:
    """Every production file spelling a Write Planner construction."""
    return {hit.rpartition(":")[0] for hit in _hits(r"WritePlanner\(", _production_sources())}


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
    _import_every_module(_all_sources())
    return sorted(
        f"{planner.__module__}.{planner.__qualname__}"
        for planner in _descendants(WritePlanner)
        if planner.__module__.startswith("parallax.")
    )


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # `build_write_planner` is the one place the optional policy modules are
    # wired in, so a second construction anywhere is a second set of strategies
    # free to drift from production's. That a lane actually REACHES this factory
    # is a different claim, graded by behavior and not asserted here.
    #
    # The first assertion is stated over the SPELLING `WritePlanner(`, and that
    # is its limit: `_P = WritePlanner` followed by `_P(...)` constructs the
    # same class under a name no text search finds. What covers that is
    # behavioral and lives in `test_planner_composition.py`, which drives a real
    # write down each lane and requires every planning the drive performed to
    # have run on a planner this factory built — which a planner constructed
    # under any spelling at all is not. File granularity for the same reason a
    # line number would be noise: which statement of `_planning.py` constructs
    # the planner is that module's own business.
    #
    # The subclass registry answers a second question exactly, and no spelling
    # bears on it: no first-party class descends from `WritePlanner`. It is not
    # a proof that no second planner exists, because an independent
    # implementation of the same interface inherits nothing and appears in no
    # registry. What forecloses one is again the drive: every write leaves
    # through this factory's planner, which is a property of the write path's
    # behavior rather than of any inventory here.
    assert _write_planner_construction_files() == {
        str((_SNAPSHOT_SRC / "handle" / "_planning.py").relative_to(PY_ROOT))
    }
    assert _write_planner_descendants() == ["parallax.core.unit_work.write_planner.WritePlanner"]
