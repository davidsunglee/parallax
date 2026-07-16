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

from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import DepositRate
from parallax.conformance.story_models import Order
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
)
