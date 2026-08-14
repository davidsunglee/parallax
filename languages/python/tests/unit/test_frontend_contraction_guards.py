"""Regression pins on the surfaces the frontend contraction removed.

Every assertion here is a property of the frontend's shape rather than of a
caller-observable behavior, so nothing in this module specifies behavior. They
are collected in one place because each one is otherwise invisible: a deleted
symbol coming back, a `registry` argument returning to the declaration surface,
or Snapshot deriving a row of its own all pass every other gate. Failures read as
"this came back", not "this is broken".

What each pin records is finished, and that is what makes them a module: a pin is
expected to sit untouched until something reverses the contraction it records.
The inventories that track `spec/python.md` §7 — a section still moving, whose
entries change as decisions are made — are `test_source_enforcement_topology.py`
instead.

Every guard is stated over something the source decides outright: what a module
imports, what it defines, what a scope declares as a parameter, whether a file
exists, whether a spelling occurs. The exact-set form is what makes any of them
useful: a guard collects the offending sites rather than counting them, so a
failure names the site of whatever is new rather than reporting that a count
moved.

A guard stated over a spelling alone is the weaker kind, because an alias evades
it. Each such guard says so where it stands and names the behavioral evidence
that covers what it admits, rather than leaving a reader to infer coverage it
does not have.

Two prohibitions the row-derivation contraction also carries are not decidable
from the source at all, and nothing here is to be read as covering them:

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
  `tests/unit/test_transaction_writes.py`.

Each asks what a value IS, or what a call at runtime REACHES, rather than how the
source spells it, and each is named again with the evidence that bears on it —
behavioral evidence, which lives with the behavior rather than here. The first is
named at the guard whose subject it borders, the second at the modules just
named. Behavior narrows these rather than closing them: an emitted statement
carries a row's content and not its provenance, and a handler is witnessed on the
path a test drives and not on the others.
"""

from __future__ import annotations

import ast
import re

import pytest
from _source_inventory_support import (
    CORE_SRC,
    ENTITY_PACKAGE,
    ENTITY_SRC,
    PACKAGES,
    SNAPSHOT_SRC,
    all_sources,
    hits,
    parsed,
    production_sources,
    site_of,
    snapshot_imports,
    sources,
    word,
)
from pydantic import BaseModel

from parallax.core.entity._entity import CHANGE_RECORD_SLOT

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
    imported = snapshot_imports()
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
        site_of(path, node.lineno)
        for path, tree in parsed(sources(SNAPSHOT_SRC))
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        and node.name in DELETED_ROW_HELPERS
    ] == []
    assert [
        (entry.importer, entry.source) for entry in imported if entry.name == "row_codec_of"
    ] == [("parallax.snapshot.handle._database", ENTITY_PACKAGE)]
    for spelling in sorted(PRIVATE_VALUE_VOCABULARY):
        assert hits(word(spelling), sources(SNAPSHOT_SRC)) == [], spelling


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
        assert hits(word(forbidden), sources(SNAPSHOT_SRC), flags=re.IGNORECASE) == [], forbidden


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
    assert hits(word(removed), production_sources()) == []


# The scopes that declare Entities and form models — the registry-based
# declaration/configuration surface's successors, and the only place a
# `registry` argument would be the removed frontend rather than a collaborator.
# `m-pk-gen`'s `sequence` registry is a real domain object elsewhere in the
# tree; nothing here is a guard against the word.
_DECLARATION_FRONTENDS = (
    ENTITY_SRC,
    CORE_SRC / "metamodel",
    CORE_SRC / "model_formation",
    PACKAGES / "parallax-descriptor" / "src" / "parallax" / "descriptor",
)


def _registry_arguments() -> list[str]:
    """Every `registry` parameter, class keyword, and keyword argument in them."""
    found: list[str] = []
    for path, tree in parsed(sources(*_DECLARATION_FRONTENDS)):
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
                taken = node.args
                found.extend(
                    site_of(path, argument.lineno)
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
                    site_of(path, keyword.value.lineno)
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
    assert not (ENTITY_SRC / "statement.py").exists()
    assert hits(rf"{ENTITY_PACKAGE}(\.| import )statement\b", all_sources()) == []
    assert hits(word("Statement"), sources(SNAPSHOT_SRC)) == []


@pytest.mark.parametrize(
    "unexported", ["EntityMeta", "ValueObjectMeta", "WireNames", "wire_names_of"]
)
def test_an_un_exported_entity_view_is_absent_from_the_package_surface(unexported: str) -> None:
    # Each name survives as implementation detail — two are metaclasses that
    # cannot be deleted — so the guard is that the package module neither
    # imports nor lists it.
    assert hits(word(unexported), sources(ENTITY_SRC / "__init__.py")) == []
