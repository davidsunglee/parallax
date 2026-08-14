"""Regression pins on the surfaces the frontend contraction removed.

Every assertion here is a property of the frontend's shape rather than of a
caller-observable behavior, so nothing in this module specifies behavior. They
are collected in one place because each is otherwise invisible: a deleted symbol
coming back, a `registry` argument returning to the declaration surface, or
Snapshot deriving a row of its own all pass every other gate. Failures read as
"this came back", not "this is broken". Each pin records one removal and is
expected to sit untouched; inventories of what `spec/python.md` §7 grants change
whenever §7's own decisions change, and are `test_source_enforcement_topology.py`
instead.

Every guard is stated over something the source decides outright — what a module
imports, defines, declares as a parameter, or names as a call's callee, whether a
file exists, whether a spelling occurs — and collects the offending sites rather
than counting them. Each is a function of the source handed to it and is shown on
both sides, over synthetic source carrying the shape it forbids and over source
that merely resembles it, because a guard exercised only against a tree that has
nothing to report cannot be told apart from one that reports nothing. A guard
stated over a bare spelling is the weaker kind, since an alias evades it, and
each such guard says so where it stands.

Two prohibitions the row-derivation contraction also carries are decidable from
no source inventory, and nothing here is to be read as covering them:

- a row derived from something other than the codec — assembled member by member
  out of ordinary attribute reads, or through Pydantic's V1 aliases, whose
  spellings (``dict``, ``json``, ``copy``, ``schema``, ``validate``,
  ``construct``) this package already uses for unrelated purposes. What it leaves
  behind is a row of raw rather than serialized values, which is a property of
  the statement a write emits and the binds it carries, and is answered where
  write behavior is — about the row's content, not its provenance;
- a handler typed broadly enough to catch a codec refusal without naming it,
  which is prohibited only where a codec call can actually reach it. Naming the
  refusal is bordered from one side: neither `EntityRowError` nor any shipped
  class descending from it reaches Snapshot's code as an imported name or as an
  attribute of a bound module, under any name a shipped module binds it by. A
  SUPERTYPE handler — `RuntimeError`, or a bare `except` — names nothing either
  reading can list, and a name read from another distribution is passed on that
  provenance rather than on what it denotes. The
  ordering it derives from — `spec/python.md` §5 decides a keyed verb's refusal
  in the shared preamble, ahead of any row derivation, so the refusal a caller
  observes carries no codec failure as its cause — is graded at the boundary by
  the compatibility cases
  ``m-unit-work-017-update-of-a-value-no-managed-read-produced`` and
  ``m-unit-work-019-write-of-a-value-another-source-produced``, and by
  `tests/unit/test_write_value_runner.py` and
  `tests/unit/test_transaction_writes.py`, where a handler is witnessed on the
  path a test drives and not on the others.
"""

from __future__ import annotations

import ast
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

import pytest
from _source_inventory_support import (
    CORE_SRC,
    ENTITY_PACKAGE,
    ENTITY_SRC,
    PACKAGES,
    SNAPSHOT_SRC,
    Import,
    all_sources,
    bound_root,
    declared_imports,
    first_party_binding_names,
    foreign_locals,
    hits,
    import_every_module,
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

from parallax.core.entity import EntityRowError
from parallax.core.entity._entity import CHANGE_RECORD_SLOT

# Row derivation: the codec answers, holding vocabulary Snapshot never holds.
#
# The free row and Change Set helpers the Entity Row Codec replaced. Absent as
# imports AND as definitions, because reintroducing one under Snapshot needs no
# import at all.
DELETED_ROW_HELPERS = frozenset(
    {"full_row", "primary_key_row", "canonical_row", "changed_fields", "effective_change_set"}
)
FORBIDDEN_ROW_IMPORTS = DELETED_ROW_HELPERS | {
    "BaseModel",
    "CHANGE_RECORD_SLOT",
    "WireNames",
}


def _codec_refusals() -> frozenset[str]:
    """Every name the codec's refusal answers to: `EntityRowError`, each shipped
    class descending from it, and every name a shipped module binds one of them
    under.

    Naming that refusal — to catch it, to rethrow it, or to translate it —
    requires one of these names, and Snapshot decides a keyed verb's refusal
    before any codec is reached. The set is taken from Python's own registries
    rather than listed: a subclass under a name of its own catches the refusal
    exactly as the base does, a re-export gives a caller a second name to import
    it by, and a list would have to be remembered.
    """
    import_every_module(all_sources())
    return first_party_binding_names(EntityRowError)


# Pydantic's internal vocabulary, read off the base class rather than listed, so
# `model_dump` and `__pydantic_fields_set__` are forbidden on the same terms as
# `model_fields_set` without anyone having had to think of them; the private
# Change Record slot joins them as the value it actually keys. The two prefixes
# are the boundary of what a spelling can decide: every other name `BaseModel`
# carries is either a name any object has or one of the V1 aliases below.
PRIVATE_VALUE_VOCABULARY = frozenset(
    name for name in dir(BaseModel) if name.startswith(("model_", "__pydantic"))
) | {CHANGE_RECORD_SLOT}


def _row_vocabulary_sites(
    over: Iterable[tuple[Path, str]], refusals: frozenset[str]
) -> list[tuple[str, str]]:
    """Each site holding part of what the Entity Row Codec holds, with what it
    holds there: an import of a name the codec owns, an import of the Pydantic
    substrate, an import of a private `parallax` name, an attribute path ending
    in one of ``refusals``, a definition of a row helper the codec replaced, or a
    spelling of Pydantic's own internals.

    The names are the codec's own, so they are held where they come FROM the
    codec's distribution: an exception another distribution exports under the same
    spelling is source that resembles the regression rather than source that is
    it. The Pydantic substrate is held by the distribution it is read from rather
    than by any name, so no re-export hides it.

    `foreign_locals` decides that on provenance alone, and this guard is no
    stronger than that reading. A refusal reached through a distribution that
    re-exports `parallax`'s own class passes, as does a genuine reach standing in
    one scope of a file that binds the spelling from elsewhere in another. Both
    need a Snapshot module to bind one of these names from outside `parallax`,
    which its one declared dependency does not export, and the prohibition itself
    is graded at the boundary by the compatibility cases and write-behavior
    modules the module docstring names.

    A refusal is looked for as an attribute path's tail as well as an imported
    name, because `import parallax.core.entity as entity` binds a module rather
    than a name and `entity.EntityRowError` then names the refusal while the
    import inventory sees only `entity`. That arm reads the parse, so prose
    discussing the refusal is left alone, and it skips a path rooted in a name the
    file binds from another distribution for the same reason the import arm does.
    The row helpers stay out of it: `self._codec.full_row(...)` IS the codec being
    consulted.
    """
    files = list(over)
    imported = list(declared_imports(iter(files)))
    trees = list(parsed(iter(files)))
    foreign = {path: foreign_locals(path, tree) for path, tree in trees}
    forbidden = FORBIDDEN_ROW_IMPORTS | refusals
    return sorted(
        [
            (one.site, held)
            for one in imported
            if one.distribution == "parallax"
            for held in forbidden & {one.name, one.local}
        ]
        + [(one.site, one.distribution) for one in imported if one.distribution == "pydantic"]
        + [
            (one.site, one.name)
            for one in imported
            if one.source.startswith("parallax") and one.name.startswith("_")
        ]
        + [
            (site_of(path, node.lineno), node.attr)
            for path, tree in trees
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr in refusals
            and bound_root(node) not in foreign[path]
        ]
        + [
            (site_of(path, node.lineno), node.name)
            for path, tree in trees
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
    # Snapshot asks the Entity Row Codec for a row and holds no part of what the
    # codec holds: not the Pydantic substrate, not the private Change Record
    # slot, not the exported side table, not the codec's own refusal, not a
    # private name out of any `parallax` module, and not a row helper of its own.
    #
    # `self._codec.full_row(...)` IS the codec being consulted, so the row
    # helpers are looked for in what Snapshot imports and defines rather than in
    # what it calls. The refusals are the names looked for as attributes too,
    # since no legitimate use of the codec's own refusal exists here at all.
    #
    # The import inventory, the attribute scan, and the definition set are exact.
    # The spelling scan is the weakest of them: it holds only for names that can
    # mean nothing but Pydantic's internals, and the names that would actually
    # derive a row are not among them.
    refusals = _codec_refusals()
    assert "EntityRowError" in refusals, "the refusal registry came back without the refusal"
    assert _row_vocabulary_sites(sources(SNAPSHOT_SRC), refusals) == []
    assert [
        (one.importer, one.source) for one in snapshot_imports() if one.name == "row_codec_of"
    ] == [("parallax.snapshot.handle._database", ENTITY_PACKAGE)]


def test_the_row_vocabulary_guard_names_what_is_held_and_passes_what_resembles_it() -> None:
    # `RowRefusal` stands for a subclass of the codec's refusal under a name of
    # its own, which catches the refusal exactly as the base does and which
    # `_codec_refusals` supplies from Python's registries; `other_library` stands
    # for a distribution of another name exporting the same spelling, which the
    # guard passes on that provenance rather than on what the name denotes.
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
                    "import parallax.core.entity as entity\n"
                    "def take(f):\n"
                    "    try: f()\n"
                    "    except entity.EntityRowError: raise\n"
                    "from parallax.core.entity import RowRefusal\n"
                    "def held(f):\n"
                    "    try: f()\n"
                    "    except refusals.RowRefusal: raise\n"
                ),
                "parallax.snapshot.handle._resembling": (
                    "from parallax.core.entity import row_codec_of\n"
                    "from pydantic_core import to_json\n"
                    '"""A refused write reports its own EntityRowError."""\n'
                    "# translating an EntityRowError here would be the regression\n"
                    "def full_row_of(value): ...\n"
                    "def dump(value): return value.model_dumped\n"
                    "def cause(failure): return failure.entity_row_error\n"
                    "from parallax.core.entity import EntityRowErrors\n"
                    "def unwrap(failure): return failure.row_refusal\n"
                    "import other_library\n"
                    "from other_library import EntityRowError\n"
                    "def elsewhere(f):\n"
                    "    try: f()\n"
                    "    except other_library.EntityRowError: raise\n"
                ),
            }
        ),
        frozenset({"EntityRowError", "RowRefusal"}),
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
            (site(12), "EntityRowError"),
            (site(13), "RowRefusal"),
            (site(16), "RowRefusal"),
        ]
    )


def _holding_site(line: int) -> str:
    return synthetic_site("parallax.snapshot.handle._holding", line)


def test_the_refusal_registry_names_a_re_export_and_passes_a_namesake(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A handler names the refusal by whatever name its own module can import it
    # by, so a subclass re-exported under a second name is a second name OF the
    # refusal and has to be forbidden under it. A class merely named like one
    # descends from nothing and contributes no name, and a subclass a test defines
    # is not shipped.
    root = type("Refusal", (), {"__module__": "parallax.core.entity.probe"})
    shipped = type("RowRefusal", (root,), {"__module__": "parallax.core.entity.probe"})
    rootless = type("SentinelRefusal", (root,), {"__module__": __name__})
    surface = ModuleType("parallax.core.entity.surface")
    vars(surface).update(
        {
            "CodecRefusal": shipped,
            "RowFailure": type("RowFailure", (), {"__module__": "parallax.core.entity.surface"}),
        }
    )
    monkeypatch.setitem(sys.modules, surface.__name__, surface)

    assert first_party_binding_names(root) == frozenset({"Refusal", "RowRefusal", "CodecRefusal"})
    assert first_party_binding_names(rootless) == frozenset()


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


# Surfaces the registry, row/provenance, and planner contractions removed.
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
    # the same thing: the name stands on its own.
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
    # the declaration surface, which survives every guard over the removed type
    # names: a parameter can return without naming `EntityRegistry` anywhere.
    # Stated over the declared argument rather than the text `registry=`, because
    # `registry: Registry | None = None` is the same surface returning with no
    # `registry=` anywhere to find.
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


STATEMENT_MODULE = f"{ENTITY_PACKAGE}.statement"


def _statement_module_imports(imported: Iterable[Import]) -> list[str]:
    """Every import of the retired transition query module, in any spelling.

    Read off the import statements rather than matched against lines, so the
    parenthesized multi-line form is seen and prose quoting the single-line form
    is not. A relative spelling from inside the Entity package reaches the same
    module as the absolute one and is seen on the same terms, since an `Import`
    carries the module it reads from absolute however it was written.
    """
    return sorted(
        one.site
        for one in imported
        if one.source == STATEMENT_MODULE
        or (one.source == ENTITY_PACKAGE and one.name == "statement")
        or (not one.source and one.name == STATEMENT_MODULE)
    )


def _retired_module_sites(root: Path, stem: str) -> list[Path]:
    """The module file ``root`` would carry ``stem`` in, if it still carries it."""
    module = root / f"{stem}.py"
    return [module] if module.exists() else []


def test_the_transition_query_statement_module_stays_absent() -> None:
    assert _retired_module_sites(ENTITY_SRC, "statement") == []
    assert _statement_module_imports(declared_imports(all_sources())) == []
    assert hits(word("Statement"), sources(SNAPSHOT_SRC)) == []


def test_the_retired_module_guard_names_the_module_and_passes_its_neighbours(
    tmp_path: Path,
) -> None:
    for neighbour in ("statement.py", "statements.py", "_statement.py"):
        (tmp_path / neighbour).write_text("", encoding="utf-8")
    assert _retired_module_sites(tmp_path, "statement") == [tmp_path / "statement.py"]


def test_the_statement_import_guard_names_the_module_and_passes_its_neighbours() -> None:
    assert _statement_module_imports(
        declared_imports(
            synthetic_sources(
                {
                    "parallax.snapshot.handle._holding": (
                        "from parallax.core.entity import statement\n"
                        "import parallax.core.entity.statement\n"
                        "from parallax.core.entity.statement import build\n"
                        "from parallax.core.entity import (\n"
                        "    statement,\n"
                        ")\n"
                        "from parallax.core.entity import statements\n"
                        "from parallax.core.entity_statement import x\n"
                        "from parallax.core.entity._statement import x\n"
                        '"""Once this read `from parallax.core.entity import statement`."""\n'
                    )
                }
            )
        )
    ) == sorted(_holding_site(line) for line in (1, 2, 3, 4))


def test_the_statement_import_guard_names_the_relative_spellings_from_inside_the_package() -> None:
    # The same imports as a module of the Entity package itself would write them,
    # where `.` names the package the retired module sat in. A package's own
    # `__init__` is one level nearer than its siblings are, so both stand here.
    module = f"{ENTITY_PACKAGE}._holding"
    package = f"{ENTITY_PACKAGE}.__init__"
    assert _statement_module_imports(
        declared_imports(
            synthetic_sources(
                {
                    module: (
                        "from . import statement\n"
                        "from .statement import build\n"
                        "from . import statements\n"
                        "from .. import statement\n"
                        "from ._statement import x\n"
                    ),
                    package: ("from . import statement\nfrom .statement import build\n"),
                }
            )
        )
    ) == sorted(synthetic_site(holder, line) for holder in (module, package) for line in (1, 2))


@pytest.mark.parametrize(
    "unexported", ["EntityMeta", "ValueObjectMeta", "WireNames", "wire_names_of"]
)
def test_an_un_exported_entity_view_is_absent_from_the_package_surface(unexported: str) -> None:
    # Each name survives as implementation detail — two are metaclasses that
    # cannot be deleted — so the guard is that the package module neither
    # imports nor lists it.
    assert hits(word(unexported), sources(ENTITY_SRC / "__init__.py")) == []
