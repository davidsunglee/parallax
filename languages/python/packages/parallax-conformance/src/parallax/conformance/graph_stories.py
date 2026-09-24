from __future__ import annotations

import datetime as dt
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from parallax.conformance.animal_owner import Person as AnimalOwnerPerson
from parallax.conformance.graph_models import Coverage, Policy
from parallax.conformance.read_models import (
    Animal,
    Balance,
    Cat,
    DepositRate,
    Document,
    Dog,
    FinancialDocument,
    Payment,
    Person,
    Pet,
    WildBoar,
)
from parallax.conformance.scripted_clock import ScriptedClock
from parallax.conformance.story_models import Order, OrderItem
from parallax.conformance.vo_models import (
    Branch,
    Customer,
    CustomerAddress,
    CustomerGeo,
    CustomerPhone,
    CustomerPoint,
    Location,
    Supplier,
)
from parallax.core.object_query import LATEST, TX_TIME
from parallax.core.unit_work import Clock
from parallax.snapshot.handle import ScopedDatabase, Snapshot, Transaction

__all__ = ["GRAPH_STORIES", "GraphStory", "graph_story_snippet"]


@dataclass(frozen=True, slots=True)
class GraphStory:
    """One executable public-API story mirroring a corpus graph-shaped case.

    ``clock`` is an optional zero-argument
    :class:`~parallax.core.unit_work.Clock` factory, carrying the same contract
    :data:`~parallax.conformance.stories.WriteStory.clock` does: a story whose
    own write takes a Transaction-Time boundary sets it so the instant it
    captures is the one its mirrored case authored, rather than whenever the
    story happened to run — the only way a composition story's read-back can be
    graded against that case's own rows. A FACTORY, not a shared instance, so
    each consumer (the fake-port no-drift guard, the real-Postgres story runner)
    drives a fresh script. ``None`` connects with the system clock.
    """

    case_id: str
    title: str
    model: str
    run: Callable[[ScopedDatabase], Any]
    clock: Callable[[], Clock] | None = None


def graph_story_snippet(story: GraphStory) -> str:
    """The story's own source — the Usage Guide snippet that cannot drift."""
    return inspect.getsource(story.run).rstrip("\n")


def diamond_identity_shares_one_child_node(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1).include(Order.items, Order.items_by_ship_date))


def back_reference_cycle_resolves_to_the_root(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1).include(Order.items.order))


def closed_world_unloaded_access_raises_without_sql(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1))  # no `.include(...)`: `statuses` stays unloaded


def empty_root_materializes_no_children(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 999).include(Order.items.statuses))


def empty_intermediate_level_short_circuits(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 4).include(Order.items.statuses))


def pinned_graph_at_a_past_valid_time_instant(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        Policy.where(Policy.all)
        .as_of(valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC), tx_time=LATEST)
        .include(Policy.coverages)
    )


def mutation_has_no_writeback(db: ScopedDatabase) -> tuple[Any, Snapshot[Any]]:
    order = db.find(Order.where(Order.id == 1)).result()
    mutated = order.edit(name="Mutant")  # in-memory only, never DML
    reread = db.find(Order.where(Order.id == 1))  # still observes the ORIGINAL name
    return mutated, reread


def an_edited_copy_keeps_its_source_nodes_views(db: ScopedDatabase) -> tuple[Snapshot[Any], Any]:
    snapshot = db.find(Order.where(Order.id == 1))  # no `.include(...)`: `statuses` stays unloaded
    edited = snapshot.result().edit(name="Mutant")  # the copy keeps the node's view state
    return snapshot, edited


def an_edit_keeps_a_loaded_relationship_view(db: ScopedDatabase) -> tuple[Snapshot[Any], Any]:
    snapshot = db.find(Order.where(Order.id == 1).include(Order.items))
    edited = snapshot.result().edit(name="Mutant")  # the copy keeps the LOADED items
    return snapshot, edited


def a_write_keeps_a_loaded_to_one_view(db: ScopedDatabase) -> tuple[Snapshot[Any], Any, Any]:
    snapshot = db.find(OrderItem.where(OrderItem.id == 11).include(OrderItem.order))
    loaded_order = snapshot.result().order

    def rewrite(tx: Transaction) -> None:
        observed = tx.find(Order.where(Order.id == 1)).result()
        tx.update(observed.edit(name="Rewritten"))

    db.transact(rewrite)
    reread = db.find(Order.where(Order.id == 1)).result()  # where the write IS observable
    return snapshot, loaded_order, reread


def a_write_keeps_a_loaded_empty_relationship_view(db: ScopedDatabase) -> Snapshot[Any]:
    snapshot = db.find(Order.where(Order.id == 3).include(Order.items))  # order 3 owns no items
    db.transact(lambda tx: tx.insert(OrderItem(id=31, order_id=3, sku="C-300", quantity=7)))
    return snapshot  # the loaded-EMPTY view is untouched by the item now in the table


def a_write_keeps_an_unloaded_relationship_absent(db: ScopedDatabase) -> Snapshot[Any]:
    snapshot = db.find(Order.where(Order.id == 3))  # no `.include(...)`: `items` stays unloaded
    db.transact(lambda tx: tx.insert(OrderItem(id=31, order_id=3, sku="C-300", quantity=7)))
    return snapshot  # absence is not emptiness, and the write does not make it one


def a_delete_keeps_a_loaded_relationship_view(
    db: ScopedDatabase,
) -> tuple[Snapshot[Any], Any, None, Snapshot[Any]]:
    snapshot = db.find(Order.where(Order.id == 1).include(Order.items))
    loaded_items = snapshot.result().items

    def destroy(tx: Transaction) -> None:
        observed = tx.find(OrderItem.where(OrderItem.id == 11)).result()
        tx.delete(observed)

    committed = db.transact(destroy)
    reread = db.find(OrderItem.where(OrderItem.order_id == 1))  # where the delete IS observable
    return snapshot, loaded_items, committed, reread


def an_edit_chain_keeps_a_loaded_relationship_view(
    db: ScopedDatabase,
) -> tuple[Snapshot[Any], Any, Any]:
    snapshot = db.find(Order.where(Order.id == 1).include(Order.items))
    renamed = snapshot.result().edit(name="Mutant")  # an AUTHORED change
    restated = renamed.edit()  # a CHANGE-FREE edit OF THAT COPY
    return snapshot, renamed, restated


def a_write_keeps_a_loaded_value_object_document(
    db: ScopedDatabase,
) -> tuple[Snapshot[Any], Any, None, Snapshot[Any]]:
    snapshot = db.find(Location.where(Location.id == 100).include(Location.customer))
    loaded_customer = snapshot.result().customer

    def rewrite(tx: Transaction) -> None:
        observed = tx.find(Customer.where(Customer.id == 1)).result()
        tx.update(
            observed.edit(
                address=CustomerAddress(  # a changed city AND the phones in the opposite order
                    street="1 Park Ave",
                    city="Bergen",
                    geo=CustomerGeo(
                        country="NO", elevation=10.5, point=CustomerPoint(lat=59.9, lon=10.7)
                    ),
                    phones=(
                        CustomerPhone(type="work", number="555-9999"),
                        CustomerPhone(type="home", number="555-1234"),
                    ),
                )
            )
        )

    committed = db.transact(rewrite)
    reread = db.find(Customer.where(Customer.id == 1))  # where the write IS observable
    return snapshot, loaded_customer, committed, reread


def a_write_keeps_a_view_over_freshly_inserted_rows(
    db: ScopedDatabase,
) -> tuple[None, Snapshot[Any], Any, None, Snapshot[Any]]:
    def create(tx: Transaction) -> None:
        tx.insert(
            Order(
                id=6,
                name="Hopper",
                sku="F-600",
                qty=2,
                price=Decimal("60.00"),
                active=True,
                ordered_on=dt.date(2024, 7, 7),
            )
        )
        tx.insert(OrderItem(id=61, order_id=6, sku="C-610", quantity=4))

    created = db.transact(create)  # PROVENANCE: the rows the graph below is made of
    snapshot = db.find(Order.where(Order.id == 6).include(Order.items))
    loaded_items = snapshot.result().items

    def rewrite(tx: Transaction) -> None:
        observed = tx.find(OrderItem.where(OrderItem.id == 61)).result()
        tx.update(observed.edit(sku="Rewritten"))

    committed = db.transact(rewrite)
    reread = db.find(OrderItem.where(OrderItem.id == 61))  # where the write IS observable
    return created, snapshot, loaded_items, committed, reread


def a_grouped_read_observes_its_own_relationship_writes(
    db: ScopedDatabase,
) -> tuple[Snapshot[Any], Snapshot[Any]]:
    def read_your_own_writes(tx: Transaction) -> tuple[Snapshot[Any], Snapshot[Any]]:
        before = tx.find(Order.where(Order.id == 1).include(Order.items))
        loaded_item = before.result().items[1]  # item 11, by the declared `id desc`
        tx.insert(OrderItem(id=13, order_id=1, sku="D-130", quantity=6))
        tx.update(loaded_item.edit(sku="Rewritten"))  # settles against the RELATIONSHIP's own row
        after = tx.find(Order.where(Order.id == 1).include(Order.items))  # sees both, uncommitted
        return before, after

    return db.transact(read_your_own_writes)


def a_multi_hop_access_drops_its_null_branches(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Order.where(Order.id == 1).include(Order.statuses.order_item))


def a_rectangle_split_keeps_a_loaded_relationship_view(
    db: ScopedDatabase,
) -> tuple[Snapshot[Any], Any, None, Snapshot[Any]]:
    pin = dt.datetime(2024, 5, 1, tzinfo=dt.UTC)
    snapshot = db.find(
        Policy.where(Policy.id == 2).as_of(valid_time=pin, tx_time=LATEST).include(Policy.coverages)
    )
    loaded_coverages = snapshot.result().coverages

    def split(tx: Transaction) -> None:
        observed = tx.find(Coverage.where(Coverage.id == 20).as_of(valid_time=LATEST)).result()
        tx.update_until(
            observed.edit(amount=Decimal("999.00")),
            valid_from=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            until=dt.datetime(2024, 9, 1, tzinfo=dt.UTC),
        )

    committed = db.transact(split)
    reread = db.find(  # the SAME pin, where the split IS observable
        Coverage.where(Coverage.policy_id == 2).as_of(valid_time=pin, tx_time=LATEST)
    )
    return snapshot, loaded_coverages, committed, reread


def a_finite_transaction_time_pinned_view_is_read_only(db: ScopedDatabase) -> None:

    def mutate_the_pinned_view(tx: Transaction) -> None:
        superseded = tx.find(
            Balance.where(Balance.id == 1).as_of(tx_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC))
        ).result()
        tx.update(superseded.edit(value=Decimal("999.00")))  # refused at the verb, before any DML

    db.transact(mutate_the_pinned_view, concurrency="optimistic")


def history_of_a_concrete_temporal_node_distinguishes_milestones(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(DepositRate.where(DepositRate.all).history(TX_TIME).as_of(valid_time=LATEST))


def one_to_one_peer_attaches_as_a_single_object(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Person.where(Person.all).include(Person.passport))


def animal_owner_reaches_root_and_narrowed_subtype_view(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.id == 10).include(
            AnimalOwnerPerson.animals, AnimalOwnerPerson.pets.narrow(Dog)
        )
    )


def narrowed_pets_view_populates_per_owner(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(AnimalOwnerPerson.pets.narrow(Dog))
    )


def equivalent_narrow_spellings_dedupe_to_one_view(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
            AnimalOwnerPerson.pets.narrow(Pet), AnimalOwnerPerson.pets.narrow(Cat, Dog)
        )
    )


def a_redundant_narrow_populates_a_view_beside_the_broad_one(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
            AnimalOwnerPerson.pets, AnimalOwnerPerson.pets.narrow(Pet)
        )
    )


def distinct_narrowed_views_populate_independently(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        AnimalOwnerPerson.where(AnimalOwnerPerson.all).include(
            AnimalOwnerPerson.pets.narrow(Dog), AnimalOwnerPerson.pets.narrow(Cat)
        )
    )


def disjoint_root_guards_fill_one_owner_view(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Animal.where(Animal.all).include(Dog.owner, Cat.owner))


def a_root_guard_beside_a_broad_path_stays_its_own_hop(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Animal.where(Animal.all).include(Animal.owner, Dog.owner))


def guarded_branches_keep_their_own_parents(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Animal.where(Animal.all).include(Dog.owner, WildBoar.owner, Dog.owner.pets))


def a_guarded_root_continues_through_a_narrowed_hop(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Animal.where(Animal.all).include(Pet.owner.pets.narrow(Dog)))


def transaction_time_only_vo_owner_as_of_latest(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Supplier.where(Supplier.all).as_of(tx_time=LATEST))


def transaction_time_only_vo_owner_as_of_a_past_instant(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        Supplier.where(Supplier.all).as_of(tx_time=dt.datetime(2024, 4, 1, tzinfo=dt.UTC))
    )


def bitemporal_vo_owner_as_of_latest(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Branch.where(Branch.all).as_of(valid_time=LATEST, tx_time=LATEST))


def bitemporal_vo_owner_as_of_a_past_audit_point(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(
        Branch.where(Branch.all).as_of(
            valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
            tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC),
        )
    )


def tph_abstract_root_read_materializes_typed_per_variant_instances(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(Payment.where(Payment.all))


def tph_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(Animal.where(Animal.narrow(Pet)))


def tph_or_across_branches_materializes_typed_per_variant_instances(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(
        Animal.where(
            Animal.narrow(Dog, where=Dog.bark_volume > 5)
            | Animal.narrow(Cat, where=Cat.indoor.is_(True))
        )
    )


def tpcs_narrow_to_abstract_subtype_materializes_typed_per_variant_instances(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(Document.where(Document.narrow(FinancialDocument)))


def customer_nested_eq_city_selects_matching_owners(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.city == "Oslo"))


def customer_deep_nested_eq_country_selects_the_matching_owner(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.geo.country == "US"))


def customer_nested_is_null_collapses_every_not_present_state(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.city.is_null()))


def customer_to_many_nested_exists_is_a_nonempty_test(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.phones.exists()))


def customer_to_many_nested_not_exists_folds_every_not_present_state(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.phones.not_exists()))


def customer_to_many_any_element_eq_matches_some_element(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.phones.type == "home"))


def customer_to_many_scoped_exists_requires_one_element_to_satisfy_both(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(
        Customer.where(
            Customer.address.phones.exists(
                CustomerPhone.type == "home", CustomerPhone.number == "555-9999"
            )
        )
    )


def customer_owner_materializes_its_whole_nested_composite(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.all))


def customer_owner_materializes_its_composite_under_a_filter(db: ScopedDatabase) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.address.city == "Oslo"))


def customer_locations_deep_fetch_materializes_the_child_document_too(
    db: ScopedDatabase,
) -> Snapshot[Any]:
    return db.find(Customer.where(Customer.all).include(Customer.locations))


def _snapshot_read_025_clock() -> Clock:
    """`m-snapshot-read-025`'s own authored Transaction Instant.

    One instant, because the story flushes one `db.transact`, and that instant
    is the `at:` its mirrored case's `updateUntil` declares — the split's three
    chained rectangles open at 2024-07-01 on the Transaction-Time axis, which is
    what lets the story's read-back be graded against the case's own rows.
    """
    return ScriptedClock([dt.datetime(2024, 7, 1, tzinfo=dt.UTC)])


GRAPH_STORIES: tuple[GraphStory, ...] = (
    GraphStory(
        "m-snapshot-read-001",
        "Diamond identity: two include paths reaching the same rows share one node",
        "orders",
        diamond_identity_shares_one_child_node,
    ),
    GraphStory(
        "m-snapshot-read-011",
        "A back-reference cycle resolves to the SAME root node",
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
        "m-snapshot-read-015",
        "An edited copy answers its source node's views, with zero SQL",
        "orders",
        an_edited_copy_keeps_its_source_nodes_views,
    ),
    GraphStory(
        "m-snapshot-read-016",
        "An edited copy holds the SAME loaded relationship objects, with zero SQL",
        "orders",
        an_edit_keeps_a_loaded_relationship_view,
    ),
    GraphStory(
        "m-snapshot-read-017",
        "A committed write leaves a loaded to-one view holding the SAME object",
        "orders",
        a_write_keeps_a_loaded_to_one_view,
    ),
    GraphStory(
        "m-snapshot-read-018",
        "A committed write leaves a loaded-EMPTY relationship loaded and empty",
        "orders",
        a_write_keeps_a_loaded_empty_relationship_view,
    ),
    GraphStory(
        "m-snapshot-read-019",
        "A committed write leaves an UNLOADED relationship absent, not empty",
        "orders",
        a_write_keeps_an_unloaded_relationship_absent,
    ),
    GraphStory(
        "m-snapshot-read-020",
        "A committed DELETE leaves the destroyed row's own node in the view that held it",
        "orders",
        a_delete_keeps_a_loaded_relationship_view,
    ),
    GraphStory(
        "m-snapshot-read-022",
        "A CHAIN of edits leaves every copy holding the SAME loaded relationship objects",
        "orders",
        an_edit_chain_keeps_a_loaded_relationship_view,
    ),
    GraphStory(
        "m-snapshot-read-023",
        "A committed write leaves a loaded view answering its own value-object document",
        "customer",
        a_write_keeps_a_loaded_value_object_document,
    ),
    GraphStory(
        "m-snapshot-read-024",
        "A view materialized over freshly inserted rows survives a write like any other",
        "orders",
        a_write_keeps_a_view_over_freshly_inserted_rows,
    ),
    GraphStory(
        "m-snapshot-read-025",
        "A bitemporal rectangle split leaves a pinned view answering its own rectangle",
        "policy",
        a_rectangle_split_keeps_a_loaded_relationship_view,
        clock=_snapshot_read_025_clock,
    ),
    GraphStory(
        "m-snapshot-read-026",
        "A fanned-out multi-hop access answers its non-null terminals alone",
        "orders",
        a_multi_hop_access_drops_its_null_branches,
    ),
    GraphStory(
        "m-unit-work-029",
        "A dependent find observes its own writes across a relationship",
        "orders",
        a_grouped_read_observes_its_own_relationship_writes,
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
        "m-inheritance-068",
        "A redundant narrow populates its own view beside the broad relationship",
        "animal",
        a_redundant_narrow_populates_a_view_beside_the_broad_one,
    ),
    GraphStory(
        "m-inheritance-074",
        "Disjoint path-root guards fetch one relationship into one view",
        "animal",
        disjoint_root_guards_fill_one_owner_view,
    ),
    GraphStory(
        "m-inheritance-075",
        "A path-root guard subsumed by a broad path stays its own hop",
        "animal",
        a_root_guard_beside_a_broad_path_stays_its_own_hop,
    ),
    GraphStory(
        "m-inheritance-076",
        "A guarded path root composes with a narrowed hop target",
        "animal",
        a_guarded_root_continues_through_a_narrowed_hop,
    ),
    GraphStory(
        "m-inheritance-078",
        "Two guarded branches over one relationship keep their own parents",
        "animal",
        guarded_branches_keep_their_own_parents,
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
