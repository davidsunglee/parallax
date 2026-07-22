"""Executable API-suite snapshot and graph stories.

Each story is ONE executable function over the **public** developer surface
(``parallax.snapshot.connect`` -> ``db.find``), mirroring one corpus
``m-snapshot-read`` (or a closely related ``m-navigate``/``m-value-object``)
case whose oracle is a materialized **graph** — a `then.graph`/`then.graphs`
document, an ``identityChecks`` reference-identity assertion, or a scenario's
own per-step observable. This is the read-side sibling of ``stories.py``'s
write stories: an example whose behavior is only observable by executing it
must run through the
shipped surface, not merely serialize a statement — a wire-level ``graph``
grade proves the assembled NEUTRAL nodes are correct, but says nothing about
the frozen-node WRAPPING (`parallax.snapshot.handle`) layered on top by
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

The Customer/Location/Depot predicate reads (`m-value-object-001/002/007/
015/016/017/019`) belong here rather than in ``read_stories.ReadStory``,
despite being
plain single-statement filters: each is classified ROW-FORM by the corpus
engine (`then.rows` alone, no `then.graph`) — the values-lane original whose
own golden SQL omits the `address` document column — but `db.find` is ALWAYS
instance-form (python.md §4: "observable as `type(node)`"), so it necessarily
projects `address` too, exactly the SAME structural non-fit
`api_suite._INHERITANCE_MULTI_CONCRETE_PROJECTION_UNREACHABLE_REASON` names
for the row-form inheritance family. Rather than leave them permanently
unreachable the way that family's row-form originals stay, the grading rule
here asserts the id/name SET the filter selects (the behavior genuinely under
test) through the real, always-instance-form developer surface, never
insisting on the inapplicable minimal row-form projection — a graph
story's bespoke per-case assertion (unlike a `ReadStory`'s generic runner,
which DOES require byte-exact golden SQL) is exactly the seam this needs.
"""

from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_models import Policy
from parallax.conformance.read_models import (
    Animal,
    Cat,
    DepositRate,
    Document,
    Dog,
    FinancialDocument,
    Payment,
    Person,
    Pet,
)
from parallax.conformance.story_models import Order
from parallax.conformance.vo_models import Branch, Customer, CustomerPhone, Supplier
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


def pinned_graph_at_a_past_valid_time_instant(db: Database) -> Snapshot[Any]:
    return db.find(
        Policy.where()
        .as_of(valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), transaction_time=LATEST)
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
        one domain key.
    """
    return db.find(DepositRate.where().history("transaction_time"))


def one_to_one_peer_attaches_as_a_single_object(db: Database) -> Snapshot[Any]:
    """Every ``Person`` materializes with its single ``Passport`` peer — a
    to-one relationship attaches as ONE object, not a collection, and a
    person with no passport (id 3) gets a null peer."""
    return db.find(Person.where().include(Person.passport))


def animal_owner_reaches_root_and_narrowed_subtype_view(db: Database) -> Snapshot[Any]:
    """The animal family's owner exposes both a root-typed
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


def transaction_time_only_vo_owner_as_of_latest(db: Database) -> Snapshot[Any]:
    """A value object rides its Transaction-Time-only owner's milestone
    (`m-value-object-028`): an Latest read returns each supplier's CURRENT
    address document — no value-object-specific temporal machinery."""
    return db.find(Supplier.where().as_of(transaction_time=LATEST))


def transaction_time_only_vo_owner_as_of_a_past_instant(db: Database) -> Snapshot[Any]:
    """The SAME owner read at a past Transaction-Time instant returns the
    SUPERSEDED address document (`m-value-object-029`) — the document rides
    the milestone exactly like a scalar column."""
    return db.find(Supplier.where().as_of(transaction_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC)))


def bitemporal_vo_owner_as_of_latest(db: Database) -> Snapshot[Any]:
    """A value object rides a FULL bitemporal owner's rectangle
    (`m-value-object-030`): pinning both dimensions to Latest returns the
    fully-current document."""
    return db.find(Branch.where().as_of(valid_time=LATEST, transaction_time=LATEST))


def bitemporal_vo_owner_as_of_a_past_audit_point(db: Database) -> Snapshot[Any]:
    """An audit read (both axes in the past, `m-value-object-031`)
    reconstructs the ORIGINALLY-believed document, distinct from what the
    system knows (`bitemporal_vo_owner_as_of_latest`)."""
    return db.find(
        Branch.where().as_of(
            valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            transaction_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        )
    )


def tph_abstract_root_read_materializes_typed_per_variant_instances(db: Database) -> Snapshot[Any]:
    """The object-lane sibling of the row-form abstract-root read
    (`m-inheritance-106`, `m-inheritance-003` its values-lane witness): each
    materialized instance is its OWN concrete class — a `CardPayment` node
    carries no `tendered` attribute at all, a `CashPayment` node no
    `card_network` — never a sibling's null-padded column."""
    return db.find(Payment.where())


def tph_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    db: Database,
) -> Snapshot[Any]:
    """The object-lane sibling of the row-form narrow-to-abstract-subtype
    read (`m-inheritance-107`, `m-inheritance-013` its values-lane witness):
    each `Dog`/`Cat` instance carries only its own declared members."""
    return db.find(Animal.where(Animal.narrow(Pet)))


def tph_or_across_branches_materializes_typed_per_variant_instances(db: Database) -> Snapshot[Any]:
    """The object-lane sibling of the row-form OR-across-branches read
    (`m-inheritance-108`, `m-inheritance-015` its values-lane witness)."""
    return db.find(
        Animal.where(
            Animal.narrow(Dog, where=Dog.bark_volume > 5)
            | Animal.narrow(Cat, where=Cat.indoor.is_(True))
        )
    )


def tpcs_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    db: Database,
) -> Snapshot[Any]:
    """The object-lane sibling of the row-form TPCS narrow-to-abstract-subtype
    read (`m-inheritance-109`, `m-inheritance-052` its values-lane witness).
    The union-all instance form is byte-identical to the row form for this
    value-object-free family, and each `Invoice`/`Receipt` instance carries
    only its own declared members."""
    return db.find(Document.where(Document.narrow(FinancialDocument)))


def customer_nested_eq_city_selects_matching_owners(db: Database) -> Snapshot[Any]:
    """A nested equality predicate through a value-object attribute
    (`m-value-object-001`): the id/name SET this filter selects is the
    behavior under test; the module docstring explains why this is a graph
    story rather than a `ReadStory`."""
    return db.find(Customer.where(Customer.address.city == "Oslo"))


def customer_deep_nested_eq_country_selects_the_matching_owner(db: Database) -> Snapshot[Any]:
    """A DEEP nested equality predicate, two levels into the composite
    (`m-value-object-002`): only Grace (Boston, US) qualifies."""
    return db.find(Customer.where(Customer.address.geo.country == "US"))


def customer_nested_is_null_collapses_every_not_present_state(db: Database) -> Snapshot[Any]:
    """A nested is-null presence test (`m-value-object-007`): the null
    column, the missing key, and the explicit JSON-null leaf all collapse to
    the SAME not-present state."""
    return db.find(Customer.where(Customer.address.city.is_null()))


def customer_to_many_nested_exists_is_a_nonempty_test(db: Database) -> Snapshot[Any]:
    """A to-many nested existence test (`m-value-object-015`): true for a row
    whose `phones` array has at least one element; every not-present state
    (empty, absent, or non-array) is excluded."""
    return db.find(Customer.where(Customer.address.phones.any()))


def customer_to_many_nested_not_exists_folds_every_not_present_state(db: Database) -> Snapshot[Any]:
    """A to-many nested absence test (`m-value-object-016`): empty, absent,
    and non-array `phones` states are all INDISTINGUISHABLE to the algebra —
    the negated sibling of `customer_to_many_nested_exists_is_a_nonempty_test`."""
    return db.find(Customer.where(Customer.address.phones.none()))


def customer_to_many_any_element_eq_matches_some_element(db: Database) -> Snapshot[Any]:
    """A flat predicate through a `many` segment is ANY-ELEMENT
    (`m-value-object-017`): true iff SOME `phones` element has `type` =
    "home"."""
    return db.find(Customer.where(Customer.address.phones.type == "home"))


def customer_to_many_scoped_exists_requires_one_element_to_satisfy_both(
    db: Database,
) -> Snapshot[Any]:
    """A scoped `where` requires ONE element to satisfy the WHOLE compound —
    SAME-element, not the unscoped AND (`m-value-object-019`): Linus's single
    phone carries both fields; Ada's carry them on DIFFERENT elements."""
    return db.find(
        Customer.where(
            Customer.address.phones.any(
                CustomerPhone.type == "home", CustomerPhone.number == "555-9999"
            )
        )
    )


def customer_owner_materializes_its_whole_nested_composite(db: Database) -> Snapshot[Any]:
    """The whole nested composite arrives WITH the owner in ONE round trip
    (`m-value-object-023`): no deep-fetch, no per-value-object fetch — the
    positive proof of the getter-navigation contract to arbitrary depth."""
    return db.find(Customer.where())


def customer_owner_materializes_its_composite_under_a_filter(db: Database) -> Snapshot[Any]:
    """The SAME materialization rides a FILTERED owner read too
    (`m-value-object-024`, the SAME `nestedEq` as
    `customer_nested_eq_city_selects_matching_owners`): materialization is
    independent of whether the owner's own read is filtered."""
    return db.find(Customer.where(Customer.address.city == "Oslo"))


def customer_locations_deep_fetch_materializes_the_child_document_too(
    db: Database,
) -> Snapshot[Any]:
    """Both the root (Customer) and the child (Location) levels of a deep
    fetch materialize their OWN value-object document (`m-deep-fetch-018`,
    design note 14 §3): the child level projects Location's own instance-form
    list (id, customer_id, label, address), decoded with LOCATION's
    descriptor — never the root's — and a null child document (Location 101)
    collapses to null exactly like a null-address Customer does at the root."""
    return db.find(Customer.where().include(Customer.locations))


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
        "A deep fetch pinned to a past Valid-Time instant materializes the superseded milestone",
        "policy",
        pinned_graph_at_a_past_valid_time_instant,
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
        "A value object rides its Transaction-Time-only owner's current milestone",
        "supplier",
        transaction_time_only_vo_owner_as_of_latest,
    ),
    GraphStory(
        "m-value-object-029",
        "A value object rides its Transaction-Time-only owner's superseded milestone",
        "supplier",
        transaction_time_only_vo_owner_as_of_a_past_instant,
    ),
    GraphStory(
        "m-value-object-030",
        "A value object rides a full bitemporal owner's fully-current rectangle",
        "branch",
        bitemporal_vo_owner_as_of_latest,
    ),
    GraphStory(
        "m-value-object-031",
        "A bitemporal audit read reconstructs the originally-believed document",
        "branch",
        bitemporal_vo_owner_as_of_a_past_audit_point,
    ),
    GraphStory(
        "m-inheritance-106",
        "A table-per-hierarchy abstract-root read materializes typed per-variant instances",
        "payment",
        tph_abstract_root_read_materializes_typed_per_variant_instances,
    ),
    GraphStory(
        "m-inheritance-107",
        "A narrow to an abstract subtype materializes typed per-variant instances",
        "animal",
        tph_narrow_to_abstract_subtype_materializes_typed_per_variant_instances,
    ),
    GraphStory(
        "m-inheritance-108",
        "An OR across two concrete-subtype branches materializes typed per-variant instances",
        "animal",
        tph_or_across_branches_materializes_typed_per_variant_instances,
    ),
    GraphStory(
        "m-inheritance-109",
        "A table-per-concrete-subtype narrow to an abstract subtype materializes "
        "typed per-variant instances",
        "document",
        tpcs_narrow_to_abstract_subtype_materializes_typed_per_variant_instances,
    ),
    GraphStory(
        "m-value-object-001",
        "A nested equality predicate through a value-object attribute",
        "customer",
        customer_nested_eq_city_selects_matching_owners,
    ),
    GraphStory(
        "m-value-object-002",
        "A DEEP nested equality predicate, two levels into the composite",
        "customer",
        customer_deep_nested_eq_country_selects_the_matching_owner,
    ),
    GraphStory(
        "m-value-object-007",
        "A nested is-null presence test collapsing every not-present state",
        "customer",
        customer_nested_is_null_collapses_every_not_present_state,
    ),
    GraphStory(
        "m-value-object-015",
        "A to-many nested existence test (non-empty)",
        "customer",
        customer_to_many_nested_exists_is_a_nonempty_test,
    ),
    GraphStory(
        "m-value-object-016",
        "A to-many nested absence test folding every not-present state",
        "customer",
        customer_to_many_nested_not_exists_folds_every_not_present_state,
    ),
    GraphStory(
        "m-value-object-017",
        "An any-element predicate through a to-many nested member",
        "customer",
        customer_to_many_any_element_eq_matches_some_element,
    ),
    GraphStory(
        "m-value-object-019",
        "A scoped to-many predicate requiring ONE element to satisfy both fields",
        "customer",
        customer_to_many_scoped_exists_requires_one_element_to_satisfy_both,
    ),
    GraphStory(
        "m-value-object-023",
        "The whole nested composite materializes with its owner in one round trip",
        "customer",
        customer_owner_materializes_its_whole_nested_composite,
    ),
    GraphStory(
        "m-value-object-024",
        "The same materialization rides a filtered owner read too",
        "customer",
        customer_owner_materializes_its_composite_under_a_filter,
    ),
    GraphStory(
        "m-deep-fetch-018",
        "A deep fetch materializes the child's own value-object document too",
        "customer",
        customer_locations_deep_fetch_materializes_the_child_document_too,
    ),
)
