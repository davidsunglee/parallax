"""Regression pins on the surfaces the frontend contraction removed.

Every assertion here is a property of the frontend's shape rather than of a
caller-observable behavior, so nothing in this module specifies behavior. They
are collected in one place because each one is otherwise invisible: a deleted
symbol coming back, a `registry` argument returning to the declaration surface,
or Snapshot deriving a row of its own all pass every other gate. Failures read as
"this came back", not "this is broken".

Each pin records one removal, so it is expected to sit untouched unless
something reverses the removal it records. Inventories of what `spec/python.md`
§7 grants change whenever §7's own decisions change, and are
`test_source_enforcement_topology.py` instead.

Every guard is stated over something the source decides outright: what a module
imports, what it defines, what a scope declares as a parameter, whether a file
exists, whether a spelling occurs. The exact-set form is what makes any of them
useful: a guard collects the offending sites rather than counting them, so a
failure names the site of whatever is new rather than reporting that a count
moved.

Each guard is a function of the source handed to it, and each is shown on both
sides: run over synthetic source carrying the shape it forbids, it names that
site, and run over source that merely resembles it, it names nothing. A guard
exercised only against a tree that has nothing to report cannot be told apart
from one that reports nothing.

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
  which is prohibited only where a codec call can actually reach it. The import
  inventory borders it from one side — naming the refusal requires importing
  `EntityRowError`, and Snapshot imports it nowhere — but a handler catching it
  through a supertype names nothing an inventory can list. The ordering it
  derives from — `spec/python.md` §5 decides a keyed verb's refusal in the shared
  preamble, ahead of any row derivation, so the refusal a caller observes carries
  no codec failure as its cause — is graded at the boundary instead, by the
  compatibility cases
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
from collections.abc import Iterable
from pathlib import Path

import pytest
from _source_inventory_support import (
    CORE_SRC,
    ENTITY_PACKAGE,
    ENTITY_SRC,
    PACKAGES,
    SNAPSHOT_SRC,
    all_sources,
    declared_imports,
    hits,
    parsed,
    production_sources,
    site_of,
    snapshot_imports,
    sources,
    synthetic_site,
    synthetic_sources,
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
# `EntityRowError` joins them as the codec's refusal vocabulary: naming that
# refusal — to catch it, to rethrow it, or to translate it — requires the name,
# and Snapshot decides a keyed verb's refusal before any codec is reached.
FORBIDDEN_ROW_IMPORTS = DELETED_ROW_HELPERS | {
    "BaseModel",
    "CHANGE_RECORD_SLOT",
    "EntityRowError",
    "WireNames",
}

# Pydantic's internal vocabulary, read off the base class rather than listed, so
# `model_dump` and `__pydantic_fields_set__` are forbidden on the same terms as
# `model_fields_set` without anyone having had to think of them; the private
# Change Record slot joins them as the value it actually keys. The two prefixes
# are the boundary of what a spelling can decide: every other name `BaseModel`
# carries is either a name any object has or one of the V1 aliases below.
PRIVATE_VALUE_VOCABULARY = frozenset(
    name for name in dir(BaseModel) if name.startswith(("model_", "__pydantic"))
) | {CHANGE_RECORD_SLOT}


def _row_vocabulary_sites(over: Iterable[tuple[Path, str]]) -> list[tuple[str, str]]:
    """Each site holding part of what the Entity Row Codec holds, with what it
    holds there: an import of a name the codec owns, an import of the Pydantic
    substrate, an import of a private `parallax` name, a definition of a row
    helper the codec replaced, or a spelling of Pydantic's own internals.
    """
    files = list(over)
    imported = list(declared_imports(iter(files)))
    return sorted(
        [
            (one.site, held)
            for one in imported
            for held in FORBIDDEN_ROW_IMPORTS & {one.name, one.local}
        ]
        + [(one.site, one.distribution) for one in imported if one.distribution == "pydantic"]
        + [
            (one.site, one.name)
            for one in imported
            if one.source.startswith("parallax") and one.name.startswith("_")
        ]
        + [
            (site_of(path, node.lineno), node.name)
            for path, tree in parsed(iter(files))
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in DELETED_ROW_HELPERS
        ]
        + [
            (site, spelling)
            for spelling in sorted(PRIVATE_VALUE_VOCABULARY)
            for site in hits(word(spelling), iter(files))
        ]
    )


def test_snapshot_holds_none_of_the_codecs_row_vocabulary() -> None:
    # Snapshot asks the Entity Row Codec for a row, and holds no part of what
    # the codec holds: not the Pydantic substrate, not the private Change Record
    # slot, not the exported side table, not the codec's own refusal, not a
    # private name out of any `parallax` module, and not a row helper of its own.
    #
    # `self._codec.full_row(...)` IS the codec being consulted, so the guard is
    # stated over what Snapshot imports, defines, and spells rather than over
    # the call.
    #
    # The import inventory and the definition set are exact. The spelling scan is
    # the weakest thing in this module: it holds for names that can mean nothing
    # but Pydantic's internals, and the names that would actually derive a row
    # are not among them. `value.dict()`, `value.json()`, and `value.copy()` are
    # V1 aliases whose spellings this package already uses for unrelated
    # purposes, so forbidding them would reject working code; a row assembled
    # member by member out of attribute reads has no distinguishing spelling at
    # all.
    #
    # What both leave behind is a row of raw rather than serialized values,
    # which is a property of the statement a write emits and the binds it
    # carries. That is a behavioral question, answered where write behavior is
    # and not by any assertion here — and answered about the row's content, not
    # about where the row came from: a row assembled anywhere else that
    # serializes identically emits the same statement and the same binds.
    assert _row_vocabulary_sites(sources(SNAPSHOT_SRC)) == []
    assert [
        (one.importer, one.source) for one in snapshot_imports() if one.name == "row_codec_of"
    ] == [("parallax.snapshot.handle._database", ENTITY_PACKAGE)]


def test_the_row_vocabulary_guard_names_what_is_held_and_passes_what_resembles_it() -> None:
    held = _row_vocabulary_sites(
        synthetic_sources(
            {
                "parallax.snapshot.handle._holding": (
                    "from parallax.core.entity import full_row, EntityRowError\n"
                    "from parallax.core.entity import canonical_row as row\n"
                    "from parallax.core.entity import row_codec_of as full_row\n"
                    "from parallax.core.entity import _codec_of\n"
                    "from pydantic import Field\n"
                    "from parallax.core.entity._entity import CHANGE_RECORD_SLOT\n"
                    "def primary_key_row(value): ...\n"
                    "def dump(value): return value.model_dump()\n"
                ),
                "parallax.snapshot.handle._resembling": (
                    "from parallax.core.entity import row_codec_of\n"
                    "from pydantic_core import to_json\n"
                    "def full_row_of(value): ...\n"
                    "def dump(value): return value.model_dumped\n"
                ),
            }
        )
    )
    site = _holding_site
    assert held == sorted(
        [
            (site(1), "EntityRowError"),
            (site(1), "full_row"),
            (site(2), "canonical_row"),
            (site(3), "full_row"),
            (site(4), "_codec_of"),
            (site(5), "pydantic"),
            (site(6), "CHANGE_RECORD_SLOT"),
            (site(7), "primary_key_row"),
            (site(8), "model_dump"),
        ]
    )


def _holding_site(line: int) -> str:
    return synthetic_site("parallax.snapshot.handle._holding", line)


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


_SPELLING_PROBE = {
    "parallax.snapshot.handle._holding": (
        "class EntityRegistry: ...\n"
        "class EntityRegistryFacet: ...\n"
        "entity_registry = None\n"
        "wire_names_of(value)\n"
        "def wire_names_of_row(value): ...\n"
        "# Temporary until the shimmer settles\n"
    )
}


def test_a_spelling_guard_names_the_bare_word_and_passes_a_longer_identifier() -> None:
    # One demonstration for every guard stated as `hits(word(...), ...)` — the
    # removed surfaces above, the transition vocabulary, the un-exported views
    # below, and the spelling half of the row vocabulary — because each decides
    # the same thing: the name stands on its own. That is also the whole of
    # their strength, since an alias spells the same class differently.
    assert hits(word("EntityRegistry"), synthetic_sources(_SPELLING_PROBE)) == [_holding_site(1)]
    assert hits(word("wire_names_of"), synthetic_sources(_SPELLING_PROBE)) == [_holding_site(4)]
    assert hits(word("shim"), synthetic_sources(_SPELLING_PROBE)) == []
    assert hits(word("temporary"), synthetic_sources(_SPELLING_PROBE)) == []
    assert hits(word("temporary"), synthetic_sources(_SPELLING_PROBE), flags=re.IGNORECASE) == [
        _holding_site(6)
    ]


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


def _registry_arguments(over: Iterable[tuple[Path, str]]) -> list[str]:
    """Every `registry` parameter, class keyword, and keyword argument in ``over``."""
    found: list[str] = []
    for path, tree in parsed(iter(list(over))):
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
    assert _registry_arguments(sources(*_DECLARATION_FRONTENDS)) == []


def test_the_registry_argument_guard_names_the_parameter_and_passes_a_collaborator() -> None:
    assert _registry_arguments(
        synthetic_sources(
            {
                "parallax.core.entity._holding": (
                    "def build(registry): ...\n"
                    "def make(*, registry=None): ...\n"
                    "class Model(Base, registry=X): ...\n"
                    "configure(registry=X)\n"
                    "take = lambda registry: registry\n"
                ),
                "parallax.core.entity._resembling": (
                    "def build(sequence_registry): ...\n"
                    "registry = load()\n"
                    "configure(registry_name=X)\n"
                    "class Model(Base, metaclass=M): ...\n"
                ),
            }
        )
    ) == sorted(synthetic_site("parallax.core.entity._holding", line) for line in range(1, 6))


STATEMENT_IMPORT = rf"{ENTITY_PACKAGE}(\.| import )statement\b"


def _retired_module_sites(root: Path, stem: str) -> list[Path]:
    """The module file ``root`` would carry ``stem`` in, if it still carries it."""
    module = root / f"{stem}.py"
    return [module] if module.exists() else []


def test_the_transition_query_statement_module_stays_absent() -> None:
    assert _retired_module_sites(ENTITY_SRC, "statement") == []
    assert hits(STATEMENT_IMPORT, all_sources()) == []
    assert hits(word("Statement"), sources(SNAPSHOT_SRC)) == []


def test_the_retired_module_guard_names_the_module_and_passes_its_neighbours(
    tmp_path: Path,
) -> None:
    for neighbour in ("statement.py", "statements.py", "_statement.py"):
        (tmp_path / neighbour).write_text("", encoding="utf-8")
    assert _retired_module_sites(tmp_path, "statement") == [tmp_path / "statement.py"]


def test_the_statement_import_guard_names_the_module_and_passes_its_neighbours() -> None:
    assert hits(
        STATEMENT_IMPORT,
        synthetic_sources(
            {
                "parallax.snapshot.handle._holding": (
                    "from parallax.core.entity import statement\n"
                    "import parallax.core.entity.statement\n"
                    "from parallax.core.entity import statements\n"
                    "from parallax.core.entity_statement import x\n"
                    "from parallax.core.entity._statement import x\n"
                )
            }
        ),
    ) == [_holding_site(1), _holding_site(2)]


@pytest.mark.parametrize(
    "unexported", ["EntityMeta", "ValueObjectMeta", "WireNames", "wire_names_of"]
)
def test_an_un_exported_entity_view_is_absent_from_the_package_surface(unexported: str) -> None:
    # Each name survives as implementation detail — two are metaclasses that
    # cannot be deleted — so the guard is that the package module neither
    # imports nor lists it.
    assert hits(word(unexported), sources(ENTITY_SRC / "__init__.py")) == []
