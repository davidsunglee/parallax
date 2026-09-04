"""What `spec/python.md` §7 records, asserted against the source it names.

§7 records which scope owns what and which reaches cross those scopes — decisions
about the source itself, which is why they are graded by reading source at all.
These assertions carry the part of §7 that import-linter's scope contracts
cannot: the private reaches §7 grants module by module, and the single
composition root a Write Planner may be built in. Each is an inventory of what §7
grants today, so an entry changes here whenever that grant changes — which is
what separates them from the pins in `test_frontend_contraction_guards.py`, each
of which records a surface the frontend removed and is expected to sit untouched.

The reaches inventoried here are exactly the ones §7 names. A reach §7 does not
name is a §7 decision before it is a code change, and the exact-set form is what
makes that true rather than merely intended: an inventory that tolerates extras
reports a number that moved, while an exact set names the site of whatever is
new and stays red until someone has decided about it.

Every inventory stated over source is a function of the source handed to it, and
is shown on both sides: run over synthetic source carrying the shape it forbids
it names that site, and run over source that merely resembles it it names
nothing. The descendant registry is the one that is not — a class's ancestry is a
runtime fact rather than a spelling, so it consumes imported classes and is
demonstrated over classes a test defines.

Two prohibitions the planner contraction carries are decidable neither from the
source nor from Python's own registries, and nothing here is to be read as
covering them: a planner constructed through an alias, which no inventory of a
name finds and no subclass registry lists; and an audit value stamped by hand
onto a row, under a name of its own, which reaches no audit strategy at all.
`tests/unit/test_planner_composition.py` narrows both by driving real writes — on
each lane it drives, every plan reaching the shared write-lowering seam came from
a planner the composition root built, and the audit port those planners hold is
the neutral one. A write lane it does not drive is covered by neither module.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import get_type_hints

from _source_inventory_support import (
    CONFORMANCE_SRC,
    ENTITY_PACKAGE,
    SNAPSHOT_SRC,
    Import,
    all_sources,
    declared_imports,
    first_party_descendants,
    import_every_module,
    parsed,
    production_sources,
    site_of,
    snapshot_imports,
    sources,
    synthetic_site,
    synthetic_sources,
)

from _support.repo import PY_ROOT
from parallax.core import sql_gen
from parallax.core.deep_fetch import ValidatedEntityQuery
from parallax.core.deep_fetch import plan as plan_deep_fetch
from parallax.core.object_query._validated import ValidatedObjectQuery
from parallax.core.predicate._validated import ValidatedPredicate
from parallax.core.sql_gen._compile import compile_read, compile_write_predicate
from parallax.core.sql_gen._write import compile_write_step
from parallax.core.unit_work import WritePlanner
from parallax.core.unit_work.instructions import (
    PreparedWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.unit_work.planned import PlannedWrite
from parallax.snapshot.handle._preflight import preflight

_PRIVATE_SQL_REACH_FENCE = "```carrier-neutral-private-reaches\n"
_CARRIER_NEUTRAL_PRIVATE_SQL_REACHES: dict[tuple[str, str], frozenset[str]] = {
    (
        "parallax.snapshot.handle._read",
        "parallax.core.sql_gen._compile",
    ): frozenset({"compile_read", "CompiledRead", "MaterializedReadRow"}),
    (
        "parallax.snapshot.handle._predicate_writes",
        "parallax.core.sql_gen._compile",
    ): frozenset({"compile_read", "CompiledRead"}),
    (
        "parallax.conformance.engine",
        "parallax.core.sql_gen._compile",
    ): frozenset({"compile_read", "CompiledRead"}),
    (
        "parallax.snapshot.handle._write_lowering",
        "parallax.core.sql_gen._write",
    ): frozenset({"compile_write_step"}),
    (
        "parallax.conformance.engine",
        "parallax.core.sql_gen._write",
    ): frozenset({"compile_write_step"}),
}


def _documented_carrier_neutral_private_sql_reaches() -> dict[tuple[str, str], frozenset[str]]:
    language_spec = (PY_ROOT / "spec" / "python.md").read_text(encoding="utf-8")
    _, marker, remainder = language_spec.partition(_PRIVATE_SQL_REACH_FENCE)
    assert marker
    body, closing, _ = remainder.partition("```\n")
    assert closing
    reaches: dict[tuple[str, str], frozenset[str]] = {}
    for row in body.splitlines():
        if not row.strip():
            continue
        module, names_text, importers_text = (cell.strip() for cell in row.split("|"))
        names = frozenset(name.strip() for name in names_text.split(","))
        for importer in importers_text.split(";"):
            reaches[(importer.strip(), module)] = names
    return reaches


def test_carrier_neutral_private_sql_reaches_match_the_language_contract() -> None:
    assert _documented_carrier_neutral_private_sql_reaches() == (
        _CARRIER_NEUTRAL_PRIVATE_SQL_REACHES
    )


def test_carrier_neutral_lowering_requires_producer_owned_semantic_products() -> None:
    assert get_type_hints(preflight)["return"] is ValidatedObjectQuery
    assert get_type_hints(plan_deep_fetch)["query"] is ValidatedObjectQuery
    assert get_type_hints(compile_read)["query"] is ValidatedEntityQuery
    assert get_type_hints(compile_write_predicate)["op"] is ValidatedPredicate
    assert get_type_hints(prepare_typed_write)["return"] == PreparedWrite
    assert get_type_hints(prepare_wire_write)["return"] == PreparedWrite
    assert get_type_hints(compile_write_step)["step"] == PlannedWrite
    assert not {
        "compile_read",
        "compile_write_predicate",
        "compile_write_step",
    }.intersection(sql_gen.__all__)


# Snapshot's reaches into `parallax.core.entity`.
#
# The enforcement unit is the scope, not a package's `__all__`, so a granted
# `parallax.core.entity` edge reaches its private modules too (`python.md` §7).
# The accepted set is therefore an inventory rather than a gate, and the
# inventory is keyed by REACHING module: §7 grants the reach to named modules,
# so a fourth module importing an already-accepted name is a new reach and a new
# §7 decision, not a use of an existing one.
#
# `_layout` and `_construction_input` are the entries here that are DECLARED
# scopes rather than private modules of the frontend: §7 gives each a row of its
# own so a runtime materializing values from stored rows can take the member
# layouts and the absence sentinel a positional row spells without the frontend's
# closure. They still appear below because the inventory reads source text, and
# every reach into an underscored module of this package is a decision worth
# spelling.
ACCEPTED_PRIVATE_ENTITY_REACHES: dict[tuple[str, str], frozenset[str]] = {
    ("parallax.snapshot._inspection", "_declaration"): frozenset(
        {"declaration_of", "is_entity_class", "members_of"}
    ),
    ("parallax.snapshot.handle._database", "_model"): frozenset({"cataloged_model", "class_index"}),
    ("parallax.snapshot.handle._page", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.handle._predicate_writes", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.handle._read", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.handle._read_scope", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.handle._stream", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.handle._write_inputs", "_declaration"): frozenset({"declaration_of"}),
    ("parallax.snapshot.handle._write_inputs", "_entity"): frozenset({"wire_names_of"}),
    ("parallax.snapshot.handle._wire_writes", "_layout"): frozenset({"CatalogedModel"}),
    ("parallax.snapshot.materialize._classify", "_layout"): frozenset({"EntityLayout"}),
    ("parallax.snapshot.materialize._convert", "_layout"): frozenset({"EntityLayout"}),
    ("parallax.snapshot.materialize._graph", "_construction_input"): frozenset({"ABSENT"}),
    ("parallax.snapshot.materialize._graph", "_layout"): frozenset({"EntityLayout"}),
    ("parallax.snapshot.materialize._merge", "_layout"): frozenset({"EntityLayout"}),
    ("parallax.snapshot.materialize._views", "_layout"): frozenset({"EntityLayout"}),
}


def _private_entity_reaches(imported: Iterable[Import]) -> dict[tuple[str, str], set[str]]:
    reached: dict[tuple[str, str], set[str]] = {}
    for one in imported:
        prefix, _, submodule = one.source.rpartition(".")
        if prefix != ENTITY_PACKAGE or not submodule.startswith("_"):
            continue
        reached.setdefault((one.importer, submodule), set()).add(one.name)
    return reached


def _entity_package_imports(imported: Iterable[Import]) -> list[str]:
    """Every ``import parallax.core.entity._x``, which binds the package rather
    than a name and so reaches a private module without appearing above."""
    return [
        one.site
        for one in imported
        if not one.source and one.name.startswith(f"{ENTITY_PACKAGE}._")
    ]


def test_snapshots_private_entity_reaches_are_exactly_the_accepted_seams() -> None:
    imported = snapshot_imports()
    assert _private_entity_reaches(imported) == {
        reach: set(names) for reach, names in ACCEPTED_PRIVATE_ENTITY_REACHES.items()
    }
    assert _entity_package_imports(imported) == []


def test_the_entity_reach_inventory_names_a_new_reach_and_passes_the_public_door() -> None:
    imported = list(
        declared_imports(
            synthetic_sources(
                {
                    "parallax.snapshot.materialize._new": (
                        "from parallax.core.entity._model import model_of\n"
                        "import parallax.core.entity._declaration\n"
                        "from ...core.entity._construction_input import UNLOADED\n"
                    ),
                    "parallax.snapshot.handle._resembling": (
                        "from parallax.core.entity import model_of, row_codec_of\n"
                        "import parallax.core.entity\n"
                        "from parallax.snapshot._inspection import declaration_of\n"
                        "from parallax.core.entity_records._model import model_of\n"
                        "from ...core.entity import row_codec_of\n"
                    ),
                }
            )
        )
    )
    assert _private_entity_reaches(imported) == {
        ("parallax.snapshot.materialize._new", "_model"): {"model_of"},
        ("parallax.snapshot.materialize._new", "_construction_input"): {"UNLOADED"},
    }
    assert _entity_package_imports(imported) == [
        synthetic_site("parallax.snapshot.materialize._new", 2)
    ]


# The conformance adapter's reaches into shipped-distribution privates.
#
# The adapter drives production through supported entry points; what remains
# below is the residue that has no supported entry point to drive, and each entry
# is a `python.md` §7 decision rather than an import someone wrote.
#
# `model_of` is an accepted private seam of production's own
# (`ACCEPTED_PRIVATE_ENTITY_REACHES` above names it for the composition root),
# whose contract calls it a first-party runtime seam rather than developer
# surface: it exists so a separately distributed frontend can read the accepted
# model out of a Domain Model, which is what these two modules do.
# `parallax.core.object_query._fluent` is the typed Object Query surface,
# deliberately absent from its own package interface so no execution module can
# reach the Entity frontend through it; a caller that WANTS the typed surface
# names the module, exactly as the snapshot handle does.
#
# The descriptor record graph is NOT here: the adapter composes corpus models
# through the public `domain_model_from_*` doors and reads the accepted model's
# own vocabulary, so no `parallax.descriptor` private module is reached at all.
#
# `cataloged_model` is one of the second-frontend fixture's two additions, and it
# subsumes `model_of` there: it drives the production find executor, which
# converts every row against the connected model's own layouts, so it takes the
# accepted model and the layout catalog paired with it through the one door
# rather than reading either half separately or building a second catalog beside
# it.
#
# That fixture is a SECOND managed value lifecycle, so it merges and constructs
# for itself rather than driving the Snapshot materializer's own private drive.
# It reaches no row walk of its own, because there is none to reach: the merge
# laid each node's member row out against the model-owned member layout the
# writer reads it against, so the row crosses `populate` by reference and the
# fixture names only the public door it goes through.
#
# Keyed by REACHING module for the same reason the snapshot inventory is.
ACCEPTED_CONFORMANCE_PRIVATE_REACHES: dict[tuple[str, str], frozenset[str]] = {
    ("parallax.conformance.case_format", "parallax.core.wire._json"): frozenset(
        {"authored_number"}
    ),
    ("parallax.conformance.engine", "parallax.core.sql_gen._compile"): frozenset(
        {"CompiledRead", "compile_read"}
    ),
    ("parallax.conformance.engine", "parallax.core.sql_gen._write"): frozenset(
        {"compile_write_step"}
    ),
    ("parallax.conformance.another_source", "parallax.snapshot.handle._preflight"): frozenset(
        {"preflight"}
    ),
    ("parallax.conformance.engine", "parallax.snapshot.handle._preflight"): frozenset(
        {"preflight"}
    ),
    ("parallax.conformance.engine", "parallax.snapshot.handle._transaction"): frozenset(
        {"buffer_prepared_predicate_write", "buffer_prepared_wire_keyed_write"}
    ),
    ("parallax.conformance.another_source", "parallax.core.entity._model"): frozenset(
        {"cataloged_model"}
    ),
    ("parallax.conformance.another_source", "parallax.core.object_query._fluent"): frozenset(
        {"ObjectQuery", "object_query_node"}
    ),
    ("parallax.conformance.models", "parallax.core.entity._model"): frozenset({"model_of"}),
}


def _conformance_private_reaches(imported: Iterable[Import]) -> dict[tuple[str, str], set[str]]:
    """Every name imported from an underscored module of a SHIPPED distribution,
    keyed by ``(importer, imported module)``.

    A module counts as private when any dotted segment after the distribution's
    top package starts with an underscore, so both
    ``parallax.core.object_query._fluent`` and a future ``parallax.core._x.y``
    are seen.
    """
    reached: dict[tuple[str, str], set[str]] = {}
    for one in imported:
        source = one.source or one.name
        if not source.startswith("parallax.") or source.startswith("parallax.conformance"):
            continue
        if not any(part.startswith("_") for part in source.split(".")[1:]):
            continue
        reached.setdefault((one.importer, source), set()).add(one.name)
    return reached


def test_conformance_private_production_reaches_are_exactly_the_accepted_seams() -> None:
    assert _conformance_private_reaches(declared_imports(sources(CONFORMANCE_SRC))) == {
        reach: set(names) for reach, names in ACCEPTED_CONFORMANCE_PRIVATE_REACHES.items()
    }


def test_the_conformance_reach_inventory_names_a_new_reach_and_passes_the_supported_doors() -> None:
    imported = declared_imports(
        synthetic_sources(
            {
                "parallax.conformance.probe": (
                    "from parallax.core.storage_layout._rules import RuleSet\n"
                    "from parallax.core._formation_profile import PROFILE\n"
                    "from parallax.core.storage_layout import StorageLayoutFacet\n"
                    "from parallax.conformance._corpus import load\n"
                    "import parallax.snapshot\n"
                )
            }
        )
    )
    assert _conformance_private_reaches(imported) == {
        ("parallax.conformance.probe", "parallax.core.storage_layout._rules"): {"RuleSet"},
        ("parallax.conformance.probe", "parallax.core._formation_profile"): {"PROFILE"},
    }


# One planner class, constructed in one module.
def _callee(node: ast.expr) -> str:
    """The name a call names its callee by, bare or as the tail of a path."""
    match node:
        case ast.Name(id=name):
            return name
        case ast.Attribute(attr=name):
            return name
        case _:
            return ""


def _write_planner_constructions(over: Iterator[tuple[Path, str]]) -> list[str]:
    """Every site calling the Write Planner class by name.

    A construction and not a mention: the name has to stand as the callee of a
    call in the parse, so an annotation, a longer class name ending in it, and
    any spelling inside a comment or a docstring are all left alone.

    The callee's tail is the whole subject, so a call qualified by any module
    counts — the question is which module holds the construction, and a class of
    that name reached from somewhere else would be one to answer, not to skip.
    Which distribution the callee's root is read from is deliberately not
    consulted: it settled no site in this tree, and it let a planner re-exported
    by another distribution, or a construction sharing a file with a foreign
    binding of the spelling, pass as though it were a namesake.

    The evasion left is the alias — `import WritePlanner as P` and `P(model)`,
    where no spelling of the class stands as a callee at all — which this module's
    own docstring hands to `test_planner_composition.py`.
    """
    found = [
        (path, node.lineno)
        for path, tree in parsed(over)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _callee(node.func) == "WritePlanner"
    ]
    return [site_of(path, line) for path, line in sorted(found)]


def _shipped_descendant_names(root: type) -> list[str]:
    """Every shipped class that is, or descends from, ``root``, by qualified name."""
    return [f"{kind.__module__}.{kind.__qualname__}" for kind in first_party_descendants(root)]


def test_build_write_planner_is_the_sole_planner_composition_root() -> None:
    # `build_write_planner` is the one place the optional policy modules are
    # wired in, so a second construction anywhere is a second set of strategies
    # free to drift from production's — including a second one inside
    # `_planning.py`, which is why the constructions are counted rather than the
    # files holding them. Their line numbers are not asserted: which statement of
    # `_planning.py` constructs the planner is that module's own business.
    #
    # The subclass registry answers a second question, and no spelling bears on
    # it: no shipped class descends from `WritePlanner`.
    constructed = _write_planner_constructions(production_sources())
    assert [site.rpartition(":")[0] for site in constructed] == [
        str((SNAPSHOT_SRC / "handle" / "_planning.py").relative_to(PY_ROOT))
    ]
    import_every_module(all_sources())
    assert _shipped_descendant_names(WritePlanner) == [
        "parallax.core.unit_work.write_planner.WritePlanner"
    ]


def test_the_construction_guard_names_every_construction_and_passes_a_mention() -> None:
    # The holding module carries the callee bare, qualified by the module it is
    # imported from, and qualified by a module of another distribution — the
    # spelling standing as a callee is the whole subject. The resembling module
    # carries the spellings that are not a construction of it: an annotation, a
    # factory whose name merely contains it, a longer class name ending in it, and
    # a longer attribute tail.
    holding = "parallax.snapshot.handle._holding"
    assert _write_planner_constructions(
        synthetic_sources(
            {
                holding: (
                    "from parallax.core.unit_work import WritePlanner\n"
                    "from parallax.core import unit_work\n"
                    "planner = WritePlanner(model)\n"
                    "second = unit_work.WritePlanner(model)\n"
                    "# a second WritePlanner(model) would be a second wiring\n"
                    '"""See :class:`WritePlanner` — built as WritePlanner(model)."""\n'
                    "import other_library\n"
                    "third = other_library.WritePlanner(model)\n"
                ),
                "parallax.snapshot.handle._resembling": (
                    "def take(planner: WritePlanner) -> None: ...\n"
                    "build_write_planner(model)\n"
                    "RecordingWritePlanner(model)\n"
                    "planners.WritePlannerFactory(model)\n"
                ),
            }
        )
    ) == [synthetic_site(holding, line) for line in (3, 4, 8)]


def test_the_descendant_registry_names_a_shipped_subclass_and_passes_a_test_one() -> None:
    root = type("Planner", (), {"__module__": "parallax.core.unit_work.probe"})
    shipped = type("WrappingPlanner", (root,), {"__module__": "parallax.snapshot.handle.probe"})
    rootless = type("SentinelPlanner", (root,), {"__module__": __name__})
    assert _shipped_descendant_names(root) == [
        "parallax.core.unit_work.probe.Planner",
        "parallax.snapshot.handle.probe.WrappingPlanner",
    ]
    assert _shipped_descendant_names(shipped) == ["parallax.snapshot.handle.probe.WrappingPlanner"]
    assert _shipped_descendant_names(rootless) == []
