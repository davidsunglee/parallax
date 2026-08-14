"""What `spec/python.md` §7 constrains, asserted against the source it names.

§7 is the only section that says anything about what the source looks like;
every other section states behavior observable at the API boundary. These
assertions carry the part of it import-linter's scope contracts cannot: the
private reaches §7 grants module by module, and the single composition root a
Write Planner may be built in. Each one tracks a spec section that is still
moving, so an entry changing here is ordinary rather than alarming — which is
what separates them from the frozen pins in
`test_frontend_contraction_guards.py`.

The reaches inventoried here are exactly the ones §7 names. A reach §7 does not
name is a §7 decision before it is a code change, and the exact-set form is what
makes that true rather than merely intended: an inventory that tolerates extras
reports a number that moved, while an exact set names the site of whatever is
new and stays red until someone has decided about it.

Most of this is stated over what the source says outright — which module an
import reads from, which files spell a construction. One assertion instead
imports every distribution and asks Python, because a class's ancestry is a
runtime fact that source text only approximates.

The construction half of the planner guard is stated over a SPELLING alone and
is the weaker kind: an alias constructs the same class under a name no text
search finds. It says so where it stands and names the behavioral evidence that
covers what it admits, rather than leaving a reader to infer coverage it does not
have.

One prohibition the planner contraction also carries is not decidable from the
source at all, and nothing here is to be read as covering it: an audit value
stamped by hand onto a row, under a name of its own, reaches no audit strategy
and so survives every assertion about how the composition root is wired. It asks
what a value IS rather than how the source spells it, and it is named again with
the evidence that bears on it in `tests/unit/test_planner_composition.py`, where
the audit strategy the composition root wires is graded — behavioral evidence,
which lives with the behavior rather than here. Behavior narrows it rather than
closing it: a stamp that never varies survives every comparison of two writes to
each other.
"""

from __future__ import annotations

from collections.abc import Iterator

from _source_inventory_support import (
    CONFORMANCE_SRC,
    ENTITY_PACKAGE,
    SNAPSHOT_SRC,
    all_sources,
    declared_imports,
    hits,
    import_every_module,
    production_sources,
    snapshot_imports,
    sources,
)

from _support.repo import PY_ROOT
from parallax.core.unit_work import WritePlanner

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
    ("parallax.snapshot.materialize._neutral", "_graph_input"): frozenset({"ValueObjectRecord"}),
}


def _private_entity_reaches() -> dict[tuple[str, str], set[str]]:
    reached: dict[tuple[str, str], set[str]] = {}
    for imported in snapshot_imports():
        prefix, _, submodule = imported.source.rpartition(".")
        if prefix != ENTITY_PACKAGE or not submodule.startswith("_"):
            continue
        reached.setdefault((imported.importer, submodule), set()).add(imported.name)
    return reached


def test_snapshots_private_entity_reaches_are_exactly_the_accepted_seams() -> None:
    assert _private_entity_reaches() == {
        reach: set(names) for reach, names in ACCEPTED_PRIVATE_ENTITY_REACHES.items()
    }
    assert [
        imported.site
        for imported in snapshot_imports()
        if not imported.source and imported.name.startswith(f"{ENTITY_PACKAGE}._")
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


def _conformance_private_reaches() -> dict[tuple[str, str], set[str]]:
    """Every name the conformance package imports from an underscored module of a
    SHIPPED distribution, keyed by ``(importer, imported module)``.

    A module counts as private when any dotted segment after the distribution's
    top package starts with an underscore, so both
    ``parallax.core.object_query._fluent`` and a future ``parallax.core._x.y``
    are seen.
    """
    reached: dict[tuple[str, str], set[str]] = {}
    for imported in declared_imports(sources(CONFORMANCE_SRC)):
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
# One planner class, constructed in one module.                               #
# --------------------------------------------------------------------------- #
def _write_planner_construction_files() -> set[str]:
    """Every production file spelling a Write Planner construction."""
    return {hit.rpartition(":")[0] for hit in hits(r"WritePlanner\(", production_sources())}


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
    import_every_module(all_sources())
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
        str((SNAPSHOT_SRC / "handle" / "_planning.py").relative_to(PY_ROOT))
    }
    assert _write_planner_descendants() == ["parallax.core.unit_work.write_planner.WritePlanner"]
