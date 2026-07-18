"""``parallax.conformance.graph_stories`` — executable API-suite snapshot/graph
stories (COR-3 Phase 7 increment 6b).

Each story is ONE executable function over the **public** developer surface
(``parallax.snapshot.connect`` -> ``db.find``), mirroring one corpus
``m-snapshot-read`` (or a closely related ``m-navigate``/``m-value-object``)
case whose oracle is a materialized **graph** — a `then.graph`/`then.graphs`
document, an ``identityChecks`` reference-identity assertion, or a scenario's
own per-step observable. This is the read-side sibling of ``stories.py``'s
write stories, needed for the SAME reason (checkpoint 3's S1 lesson): an
example whose behavior is only observable by EXECUTING it must run through the
shipped surface, not merely serialize a statement — a wire-level ``graph``
grade proves the assembled NEUTRAL nodes are correct, but says nothing about
the frozen-node WRAPPING (`parallax.snapshot.wrap`) layered on top by
``db.find`` — identity surviving the wrap, `is_loaded`/
`UnloadedRelationshipError`, closed-world zero-SQL access, `pin_of`/`edge_of`
on a materialized node. Those developer-facing guarantees are exactly what the
API Conformance Suite exists to prove (`m-api-conformance` "Two proof paths").

Each story's own source is the Usage Guide snippet (`graph_story_snippet`,
mirroring `stories.story_snippet`) and is ALSO what
``tests/api_conformance/test_story_run.py`` executes against real Postgres —
one source, both consumers, so the documented spelling cannot drift from the
executed one. Grading is bespoke per story (unlike the write stories' shared
row/table-state comparators): a graph story returns whatever its own
docstring-free body naturally computes — a `Snapshot[T]`, a node, or a
`(before, after)` pair — and the test file's own per-case assertion (named
after the story) is the oracle, chosen to mirror the mirrored case's own
`then.graph`/`identityChecks`/scenario observable as closely as one assertion
can. Two lifecycle observables this module's stories witness —
`sameObjectAs`/`differentObjectFrom` reference identity and the closed-world
`UnloadedRelationshipError` — are the SAME per-language guarantees
`m-api-conformance` requirement 4 names as needing to be "graded, not
narrated" here.

A function defined here but NOT listed in ``GRAPH_STORIES`` is a SUPPLEMENTAL
proof: a public-API-only demonstration ``test_story_run.py`` still executes
and grades directly (never through the ``GraphStory``/``Example`` machinery),
proving a capability alongside a case's own exercised example without being
counted toward that (or any) case's exercised status — see
`history_of_a_concrete_temporal_node_distinguishes_milestones`.
"""

from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import Cat, DepositRate, Dog, Person, Pet
from parallax.conformance.story_models import Order
from parallax.conformance.vo_models import Branch, Supplier
from parallax.core.temporal_read import LATEST
from parallax.snapshot.handle import Database, Snapshot

__all__ = ["GRAPH_STORIES", "GraphStory", "graph_story_snippet"]


@dataclass(frozen=True, slots=True)
class GraphStory:
    """One executable public-API story mirroring a corpus graph-shaped case."""

    case_id: str
    title: str
    model: str
    run: Callable[[Database], Any]


def graph_story_snippet(story: GraphStory) -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return inspect.getsource(story.run).rstrip("\n")


def diamond_identity_shares_one_child_node(db: Database) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1).include(Order.items, Order.items_by_ship_date))


def back_reference_cycle_resolves_to_the_root(db: Database) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1).include(Order.items.order))


def closed_world_unloaded_access_raises_without_sql(db: Database) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1))  # no `.include(...)`: `statuses` stays unloaded


def empty_root_materializes_no_children(db: Database) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 999).include(Order.items.statuses))


def empty_intermediate_level_short_circuits(db: Database) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 4).include(Order.items.statuses))


def pinned_graph_at_a_past_business_instant(db: Database) -> Snapshot[Any]:
    return db.find(
        Policy.where()
        .as_of(business=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), processing=LATEST)
        .include(Policy.coverages)
    )


def mutation_has_no_writeback(db: Database) -> tuple[Any, Snapshot[Any]]:
    order = db.find(Order.where(Order.id == 1)).result()
    mutated = order.model_copy(update={"name": "Mutant"})  # in-memory only, never DML
    reread = db.find(Order.where(Order.id == 1))  # still observes the ORIGINAL name
    return mutated, reread


def history_of_a_concrete_temporal_node_distinguishes_milestones(db: Database) -> Snapshot[Any]:
    """SUPPLEMENTAL — not a registered ``GraphStory`` and not counted toward any
    case's exercised status (`m-inheritance-100`'s own point read is exercised
    by its `ReadStory`, `parallax.conformance.read_stories`, graded by
    ``test_read_story_runs_through_the_shipped_surface``). Proves the separate
    milestone-HISTORY shape: `DepositRate` declares no `as_of` of its own
    (`Rate`, the family root, does); `.history(...)` still accepts
    `DepositRate`'s own inherited axis spelling, and the strengthened
    ``fixtures/rate.yaml`` milestone history surfaces the closed historical
    correction and the current row as two distinct, edge-pinned nodes sharing
    one business key.
    """
    return db.find(DepositRate.where().history(axis="processing"))


def one_to_one_peer_attaches_as_a_single_object(db: Database) -> Snapshot[Any]:
    """Every ``Person`` materializes with its single ``Passport`` peer — a
    to-one relationship attaches as ONE object, not a collection, and a
    person with no passport (id 3) gets a null peer."""
    return db.find(Person.where().include(Person.passport))


def animal_owner_reaches_root_and_narrowed_subtype_view(db: Database) -> Snapshot[Any]:
    """The animal family's REAL owner (ledger D-20): a root-typed
    ``animals`` path (reaching any concrete subtype) and a leaf-typed
    ``pets[Dog]`` narrowed view both reach the SAME row (Alice's Rex) with
    DIFFERENT fetched projections — the family-normalized,
    projection-independent diamond (`m-snapshot-read-012`)."""
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.id == 10).include(
            AnimalOwnerPerson.animals, AnimalOwnerPerson.pets.narrow(Dog)
        )
    )


def narrowed_pets_view_populates_per_owner(db: Database) -> Snapshot[Any]:
    """A single narrowed ``pets[Dog]`` view over every owner (`m-inheritance-065`):
    the narrowed hop populates a distinct view keyed by the derived name,
    never marking the broad ``pets`` relationship loaded."""
    return db.find(AnimalOwnerPerson.where().include(AnimalOwnerPerson.pets.narrow(Dog)))


def equivalent_narrow_spellings_dedupe_to_one_view(db: Database) -> Snapshot[Any]:
    """Two DIFFERENT authored narrowings resolving to the SAME effective
    concrete set dedupe to ONE hop (`m-inheritance-066`): ``narrow(Pet)`` and
    ``narrow(Cat, Dog)`` both derive the view key ``pets[Cat,Dog]``."""
    return db.find(
        AnimalOwnerPerson.where().include(
            AnimalOwnerPerson.pets.narrow(Pet), AnimalOwnerPerson.pets.narrow(Cat, Dog)
        )
    )


def distinct_narrowed_views_populate_independently(db: Database) -> Snapshot[Any]:
    """Two narrowings to DIFFERENT concrete sets stay two distinct views
    (`m-inheritance-067`): ``pets[Dog]`` and ``pets[Cat]`` populate
    independently (dedup identity is the effective concrete set, not the
    bare relationship hop)."""
    return db.find(
        AnimalOwnerPerson.where().include(
            AnimalOwnerPerson.pets.narrow(Dog), AnimalOwnerPerson.pets.narrow(Cat)
        )
    )


def unitemporal_vo_owner_as_of_now(db: Database) -> Snapshot[Any]:
    """A value object rides its unitemporal-processing owner's milestone
    (`m-value-object-028`): an as-of-now read returns each supplier's CURRENT
    address document — no value-object-specific temporal machinery."""
    return db.find(Supplier.where().as_of(processing=LATEST))


def unitemporal_vo_owner_as_of_a_past_instant(db: Database) -> Snapshot[Any]:
    """The SAME owner read at a past processing instant returns the
    SUPERSEDED address document (`m-value-object-029`) — the document rides
    the milestone exactly like a scalar column."""
    return db.find(Supplier.where().as_of(processing=dt.datetime(2024, 4, 1, tzinfo=dt.UTC)))


def bitemporal_vo_owner_as_of_now_both_axes(db: Database) -> Snapshot[Any]:
    """A value object rides a FULL bitemporal owner's rectangle
    (`m-value-object-030`): pinning both axes to now returns the
    fully-current document."""
    return db.find(Branch.where().as_of(business=LATEST, processing=LATEST))


def bitemporal_vo_owner_as_of_a_past_audit_point(db: Database) -> Snapshot[Any]:
    """An audit read (both axes in the past, `m-value-object-031`)
    reconstructs the ORIGINALLY-believed document, distinct from what the
    system knows now (`bitemporal_vo_owner_as_of_now_both_axes`)."""
    return db.find(
        Branch.where().as_of(
            business=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        )
    )


GRAPH_STORIES: tuple[GraphStory, ...] = (
    GraphStory(
        "m-snapshot-read-001",
        "Diamond identity: two include paths reaching the same rows share one node",
        "orders",
        diamond_identity_shares_one_child_node,
    ),
    GraphStory(
        "m-snapshot-read-011",
        "A back-reference cycle resolves to the SAME root node (identityChecks)",
        "orders",
        back_reference_cycle_resolves_to_the_root,
    ),
    GraphStory(
        "m-snapshot-read-009",
        "Closed-world: an un-included relationship raises with zero SQL",
        "orders",
        closed_world_unloaded_access_raises_without_sql,
    ),
    GraphStory(
        "m-snapshot-read-004",
        "An empty root elides every child statement",
        "orders",
        empty_root_materializes_no_children,
    ),
    GraphStory(
        "m-snapshot-read-005",
        "An empty intermediate level short-circuits the grandchild fetch",
        "orders",
        empty_intermediate_level_short_circuits,
    ),
    GraphStory(
        "m-navigate-013",
        "A deep fetch pinned to a past business instant materializes the superseded milestone",
        "policy",
        pinned_graph_at_a_past_business_instant,
    ),
    GraphStory(
        "m-snapshot-read-010",
        "Mutating a snapshot node never writes back",
        "orders",
        mutation_has_no_writeback,
    ),
    GraphStory(
        "m-snapshot-read-007",
        "A one-to-one peer attaches as a single object, not a collection",
        "person",
        one_to_one_peer_attaches_as_a_single_object,
    ),
    GraphStory(
        "m-snapshot-read-012",
        "Family-normalized, projection-independent diamond over a real animal-family owner",
        "animal",
        animal_owner_reaches_root_and_narrowed_subtype_view,
    ),
    GraphStory(
        "m-inheritance-065",
        "A single narrowed subtype view over a table-per-hierarchy family",
        "animal",
        narrowed_pets_view_populates_per_owner,
    ),
    GraphStory(
        "m-inheritance-066",
        "Equivalent authored narrowings dedupe to the same derived view",
        "animal",
        equivalent_narrow_spellings_dedupe_to_one_view,
    ),
    GraphStory(
        "m-inheritance-067",
        "Two distinct narrowed views over the same relationship populate independently",
        "animal",
        distinct_narrowed_views_populate_independently,
    ),
    GraphStory(
        "m-value-object-028",
        "A value object rides its unitemporal-processing owner's current milestone",
        "supplier",
        unitemporal_vo_owner_as_of_now,
    ),
    GraphStory(
        "m-value-object-029",
        "A value object rides its unitemporal-processing owner's superseded milestone",
        "supplier",
        unitemporal_vo_owner_as_of_a_past_instant,
    ),
    GraphStory(
        "m-value-object-030",
        "A value object rides a full bitemporal owner's fully-current rectangle",
        "branch",
        bitemporal_vo_owner_as_of_now_both_axes,
    ),
    GraphStory(
        "m-value-object-031",
        "A bitemporal audit read reconstructs the originally-believed document",
        "branch",
        bitemporal_vo_owner_as_of_a_past_audit_point,
    ),
)
