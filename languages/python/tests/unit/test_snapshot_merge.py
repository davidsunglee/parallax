"""Projection merging and Entity graph construction over the sealed Snapshot graph.

Drives the production materializer end to end — merge, allocate, populate, and
the per-node state factory — over graphs built exactly as a read driver
builds them: diamond collapse onto one instance, cycle closure by object
identity, narrowed views across every authoring route, loaded-null versus
loaded-empty versus unloaded, polymorphic concrete-class resolution, Value Object
construction, whole-graph pin and per-node edge, and the first-projection-wins /
view-union split the merge is stated in.

Per-row conversion lives in `test_snapshot_conversion.py`; the inspection surface
these assertions read through has its own suite in `test_snapshot_inspection.py`.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import IntEnum
from typing import Any, cast

import pytest
from _snapshot_graph_support import GraphFixture, invalid_record

from _support import snapshot_models as sm
from parallax.conformance import read_models, vo_models
from parallax.conformance.story_models import ORDERS_MODEL
from parallax.conformance.story_models import Order as _soOrder
from parallax.conformance.story_models import OrderItem as _soOrderItem
from parallax.core import (
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    ValueObject,
    attr,
)
from parallax.core.entity import GraphConstructionError, RelationshipPath
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, RelationshipIdentity
from parallax.core.object_query import IncludeSegment
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey
from parallax.snapshot import SnapshotInspectionError, edge_of, is_view_loaded, pin_of, view
from parallax.snapshot.materialize import (
    InvalidRootInput,
    RelationshipViewKey,
    StoredDataIssueInput,
    merge_graph_input,
)
from parallax.snapshot.materialize._graph import ABSENT, GraphBuilder

_ORDERS = sm.SNAP_ORDERS_MODEL
_ANIMAL = sm.ANIMAL_MODEL
_STORY_ORDERS = ORDERS_MODEL
_DOCUMENT = read_models.DOCUMENT_MODEL
_NAMESPACE = "parallax.compatibility"

_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": "A",
    "qty": 1,
    "price": Decimal("1"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
_ITEM_ROW: dict[str, object] = {
    "id": 11,
    "order_id": 1,
    "sku": "x",
    "quantity": 1,
    "shipped_on": None,
}
_DOG_ROW: dict[str, object] = {
    "id": 1,
    "name": "Rex",
    "owner_id": 10,
    "license_id": "L-100",
    "bark_volume": 7,
}
_CAT_ROW: dict[str, object] = {
    "id": 2,
    "name": "Tom",
    "owner_id": 10,
    "license_id": None,
    "indoor": True,
}


# --------------------------------------------------------------------------- #
# Construction: frozen instances, closed-world arms, cycle closure.            #
# --------------------------------------------------------------------------- #
def test_a_merged_node_becomes_a_frozen_instance_of_its_registered_class() -> None:
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    (root,) = fixture.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert (root.id, root.name, root.price) == (1, "Ada", Decimal("1"))


def test_an_included_to_many_is_a_tuple_and_its_back_reference_closes_the_cycle() -> None:
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    item = fixture.node("SnapOrderItem", _ITEM_ROW)
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (item,))
    fixture.attach(item, "parallax.compatibility.SnapOrderItem.order", order)
    (root,) = fixture.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert isinstance(root.items, tuple)
    assert root.items[0].id == 11
    assert root.items[0].order is root


def test_a_relationship_no_projection_carried_stays_unloaded() -> None:
    fixture = GraphFixture(_ORDERS)
    (root,) = fixture.materialize(fixture.node("SnapOrder", _ORDER_ROW))
    assert isinstance(root, sm.SnapOrder)
    assert is_view_loaded(root, sm.SnapOrder.items) is False


def test_loaded_null_and_loaded_empty_are_distinct_from_unloaded() -> None:
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    item = fixture.node("SnapOrderItem", _ITEM_ROW)
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", ())
    fixture.attach(item, "parallax.compatibility.SnapOrderItem.order", None)
    root, orphan = fixture.materialize(order, item)
    assert isinstance(root, sm.SnapOrder)
    assert isinstance(orphan, sm.SnapOrderItem)
    assert root.items == ()
    assert is_view_loaded(root, sm.SnapOrder.items) is True
    assert orphan.order is None
    assert is_view_loaded(orphan, sm.SnapOrderItem.order) is True


def test_roots_publish_in_the_order_they_were_given() -> None:
    # Every `find` today answers a single-root graph, so root order is a
    # structural consequence there rather than a pinned property; a multi-root
    # graph is what states it.
    fixture = GraphFixture(_ORDERS)
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2, "name": "Linus"})
    roots = cast("tuple[Any, ...]", fixture.materialize(second, first))
    assert [root.id for root in roots] == [2, 1]


def test_an_invalid_root_preserves_its_result_position_without_allocating_a_node() -> None:
    # The keyless row sits BETWEEN two valid ones, so the hole it leaves is a
    # result position rather than a truncation, and the two survivors keep the
    # allocation indices their own walk order gives them.
    fixture = GraphFixture(_ORDERS)
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2, "name": "Linus"})

    merge = merge_graph_input(fixture.graph(first, keyless, second))
    assert merge.roots == (0, None, 1)
    assert [issue.code for record in merge.invalid_roots for issue in record.issues] == [
        "stored-data-primary-key-null"
    ]
    assert [record.ordinal for record in merge.invalid_roots] == [1]
    assert merge.order == (
        EntityIdentity(_NAMESPACE, "SnapOrder"),
        EntityIdentity(_NAMESPACE, "SnapOrder"),
    )


def test_invalid_root_carriers_require_a_position_and_an_issue() -> None:
    issue = StoredDataIssueInput(
        "stored-data-primary-key-null",
        EntityIdentity(_NAMESPACE, "SnapOrder"),
    )
    with pytest.raises(ValueError, match="nonnegative"):
        InvalidRootInput(-1, (issue,))
    with pytest.raises(ValueError, match="at least one"):
        InvalidRootInput(0, ())


def test_an_invalid_root_ordinal_is_its_result_position_by_construction() -> None:
    # A caller never spells one: sealing derives the ordinal from the position
    # the root occupies, so the mismatch a whole-graph validation pass used to
    # look for is unrepresentable rather than checked.
    fixture = GraphFixture(_ORDERS)
    valid = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    merge = merge_graph_input(fixture.graph(valid, keyless))
    assert [record.ordinal for record in merge.invalid_roots] == [1]


# --------------------------------------------------------------------------- #
# Diamond projection merge: two SIBLING include paths reach the SAME logical    #
# row through two DIFFERENT projections (a driver never dedupes across sibling  #
# levels — each attach position converts its own row). `Order`/`OrderItem`      #
# declare TWO sibling relationships over the same join (`items` /               #
# `itemsByShipDate`), the shape m-snapshot-read-001 itself exercises.           #
# --------------------------------------------------------------------------- #
def test_a_diamond_collapses_onto_one_instance_and_unions_the_views() -> None:
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    via_items = fixture.node("OrderItem", _ITEM_ROW)
    via_ship_date = fixture.node("OrderItem", _ITEM_ROW)
    fixture.attach(order, "parallax.compatibility.Order.items", (via_items,))
    fixture.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))
    # Only the SECOND path loaded the back-reference: the union is what carries it.
    fixture.attach(via_ship_date, "parallax.compatibility.OrderItem.order", order)
    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0] is root.items_by_ship_date[0]
    assert is_view_loaded(root.items[0], _soOrderItem.order) is True
    assert root.items[0].order is root


def test_a_view_both_projections_carried_wires_exactly_once() -> None:
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    via_items = fixture.node("OrderItem", _ITEM_ROW)
    via_ship_date = fixture.node("OrderItem", _ITEM_ROW)
    fixture.attach(order, "parallax.compatibility.Order.items", (via_items,))
    fixture.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))
    fixture.attach(via_items, "parallax.compatibility.OrderItem.order", order)
    fixture.attach(via_ship_date, "parallax.compatibility.OrderItem.order", order)
    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0] is root.items_by_ship_date[0]
    assert root.items[0].order is root


def test_each_to_many_view_keeps_its_own_order_through_the_merge() -> None:
    # The diamond's two views are ordered differently by their own declared
    # `orderBy`, and both reach the same two logical rows. Merging shares one
    # instance per row, so a per-view order that survived only because the two
    # tuples happened to hold distinct objects would be indistinguishable from
    # one that did not — which is what a REVERSED sibling states.
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    first_by_id = fixture.node("OrderItem", {**_ITEM_ROW, "id": 12, "sku": "later"})
    second_by_id = fixture.node("OrderItem", _ITEM_ROW)
    first_by_ship_date = fixture.node("OrderItem", _ITEM_ROW)
    second_by_ship_date = fixture.node("OrderItem", {**_ITEM_ROW, "id": 12, "sku": "later"})
    fixture.attach(order, "parallax.compatibility.Order.items", (first_by_id, second_by_id))
    fixture.attach(
        order,
        "parallax.compatibility.Order.itemsByShipDate",
        (first_by_ship_date, second_by_ship_date),
    )
    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)
    assert [item.id for item in root.items] == [12, 11]
    assert [item.id for item in root.items_by_ship_date] == [11, 12]
    assert root.items[0] is root.items_by_ship_date[1]
    assert root.items[1] is root.items_by_ship_date[0]


def test_a_scalar_the_first_projection_carries_wins_without_comparison() -> None:
    # Duplicate projections of one logical node are value-identical by
    # construction — same row, same pin — so the merge takes the first entry it
    # sees and compares nothing. A second projection carrying a DIFFERENT value
    # is unreachable through a read; what the assertion pins is that no
    # comparison happens and no refusal is raised.
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    first = fixture.node("OrderItem", _ITEM_ROW)
    second = fixture.node("OrderItem", {**_ITEM_ROW, "sku": "y"})
    fixture.attach(order, "parallax.compatibility.Order.items", (first,))
    fixture.attach(order, "parallax.compatibility.Order.itemsByShipDate", (second,))
    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0].sku == "x"


def test_duplicate_projections_preserve_each_physical_stored_data_issue() -> None:
    # Two sibling levels can project one invalid row twice. Merge retains both
    # physical findings; per-root classification owns any later deduplication.
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    invalid_row = {**_ITEM_ROW, "shipped_on": "not-a-date"}
    via_items = fixture.node("OrderItem", invalid_row)
    via_ship_date = fixture.node("OrderItem", invalid_row)
    fixture.attach(order, "parallax.compatibility.Order.items", (via_items,))
    fixture.attach(
        order,
        "parallax.compatibility.Order.itemsByShipDate",
        (via_ship_date,),
    )

    merge = merge_graph_input(fixture.graph(order))
    item = _sole_node(merge, "OrderItem")
    assert len(merge.issues(item)) == 2
    assert merge.issues(item)[0].code == "stored-data-leaf-undecodable"


def test_an_invalid_descendant_classifies_the_reachable_root() -> None:
    # Classification is root-granular: a clean root cannot hide an invalid
    # included child merely because the root's own members are constructible,
    # and the child's undecodable leaf leaves no value to hydrate the root from.
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    invalid = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    fixture.attach(order, "parallax.compatibility.Order.items", (invalid,))

    published = invalid_record(fixture.materialize(order)[0])
    assert published.data is None
    assert {(issue.code, issue.member) for issue in published.issues} == {
        (
            "stored-data-leaf-undecodable",
            AttributeIdentity(EntityIdentity(_NAMESPACE, "OrderItem"), "shippedOn"),
        )
    }
    assert published.object_key == ObjectKey(EntityIdentity(_NAMESPACE, "Order"), (("id", 1),))


def test_an_unrequested_invalid_projection_does_not_refuse_a_clean_root() -> None:
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})

    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)


def test_an_invalid_descendant_key_never_enters_logical_identity() -> None:
    # A child with no usable primary key remains a classified projection rather
    # than being merged under a synthetic `(None,)` logical key.
    fixture = GraphFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    invalid = fixture.node("OrderItem", {**_ITEM_ROW, "id": None})
    fixture.attach(order, "parallax.compatibility.Order.items", (invalid,))

    merge = merge_graph_input(fixture.graph(order))
    item = _sole_node(merge, "OrderItem")
    assert [issue.code for issue in merge.issues(item)] == ["stored-data-primary-key-null"]
    published = invalid_record(fixture.materialize(order)[0])
    assert published.data is None
    # The child's own identity never decoded, so its diagnosis locates no object
    # while the root's record still locates the result position it invalidated.
    assert [issue.object_key for issue in published.issues] == [None]


# --------------------------------------------------------------------------- #
# Polymorphic concrete resolution and narrowed views.                          #
# --------------------------------------------------------------------------- #
def test_polymorphic_children_materialize_as_their_concrete_classes() -> None:
    fixture = GraphFixture(_ANIMAL)
    owner = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    cat = fixture.node("Cat", _CAT_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.animals", (dog, cat))
    (root,) = fixture.materialize(owner)
    assert isinstance(root, sm.AnimalOwner)
    reached_dog, reached_cat = root.animals
    assert (type(reached_dog), type(reached_cat)) == (sm.Dog, sm.Cat)
    assert cast("sm.Dog", reached_dog).bark_volume == 7
    assert cast("sm.Cat", reached_cat).indoor is True


def test_a_narrowed_view_is_independent_of_the_broad_relationship() -> None:
    fixture = GraphFixture(_ANIMAL)
    owner = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    (root,) = fixture.materialize(owner)
    assert isinstance(root, sm.AnimalOwner)
    path = sm.AnimalOwner.pets.narrow(sm.Dog)
    assert is_view_loaded(root, sm.AnimalOwner.pets) is False
    assert is_view_loaded(root, path) is True
    narrowed = cast("tuple[object, ...]", view(root, path))
    assert type(narrowed[0]) is sm.Dog
    with pytest.raises(SnapshotInspectionError) as unrelated:
        is_view_loaded(root, sm.SnapOrder.items)
    assert unrelated.value.code == "snapshot-view-owner-mismatch"


def test_two_narrowed_views_coexist_independently_on_one_node() -> None:
    fixture = GraphFixture(_ANIMAL)
    owner = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    cat = fixture.node("Cat", _CAT_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (cat,), narrowed="pets[Cat]")
    (root,) = fixture.materialize(owner)
    dogs = cast("tuple[object, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    cats = cast("tuple[object, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Cat)))
    assert (type(dogs[0]), type(cats[0])) == (sm.Dog, sm.Cat)


def test_every_authoring_route_to_one_narrowed_view_reaches_the_same_value() -> None:
    # A `RelationshipPath` is a frozen value carrying nothing but its segments,
    # its target spelling and its source, so a directly built path and a copy
    # each key the same view as the class-derived one.
    fixture = GraphFixture(_ANIMAL)
    owner = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    (root,) = fixture.materialize(owner)
    derived = sm.AnimalOwner.pets.narrow(sm.Dog)
    direct: RelationshipPath[sm.AnimalOwner, sm.Dog] = RelationshipPath(
        segments=(
            IncludeSegment(rel="parallax.compatibility.AnimalOwner.pets", narrow_to=("Dog",)),
        ),
        target="Dog",
    )
    for path in (derived, direct):
        reached = cast("tuple[object, ...]", view(root, path))
        assert type(reached[0]) is sm.Dog


def test_a_narrowed_to_one_view_carries_a_single_node_or_loaded_null() -> None:
    fixture = GraphFixture(_ANIMAL)
    alice = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": 1})
    bob = fixture.node("AnimalOwner", {"id": 11, "name": "Bob", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    fixture.attach(
        alice, "parallax.compatibility.AnimalOwner.favorite", dog, narrowed="favorite[Dog]"
    )
    fixture.attach(
        bob, "parallax.compatibility.AnimalOwner.favorite", None, narrowed="favorite[Dog]"
    )
    first, second = fixture.materialize(alice, bob)
    assert type(view(first, sm.AnimalOwner.favorite.narrow(sm.Dog))) is sm.Dog
    assert view(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is None


def test_a_table_per_concrete_subtype_row_materializes_its_resolved_concrete() -> None:
    # A table-per-concrete-subtype position resolving to exactly ONE concrete
    # emits no `familyVariant` at all (`m-sql`'s `_compile_tpcs_single`); the
    # concrete Entity the compiled read resolved is what still selects the class.
    fixture = GraphFixture(_DOCUMENT)
    invoice = fixture.node(
        "Invoice",
        {
            "id": 1,
            "title": "Invoice-A",
            "folder_id": None,
            "currency": "USD",
            "amount_due": Decimal("120.00"),
        },
    )
    (root,) = fixture.materialize(invoice)
    assert type(root) is read_models.Invoice
    assert root.amount_due == Decimal("120.00")


# --------------------------------------------------------------------------- #
# Value Object construction.                                                   #
# --------------------------------------------------------------------------- #
def test_entity_level_value_object_members_construct_into_their_declared_classes() -> None:
    fixture = GraphFixture(_ORDERS)
    status = fixture.node(
        "SnapOrderStatus",
        {
            "id": 1,
            "order_id": 1,
            "order_item_id": None,
            "code": "shipped",
            "primary_tag": None,
            "tags": [
                {"label": "a", "detail": {"note": "x"}, "details": [{"note": "y"}]},
                {"label": "b"},
            ],
        },
    )
    (root,) = fixture.materialize(status)
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.primary_tag is None
    first, second = root.tags
    assert (first.label, first.detail, first.details) == (
        "a",
        sm.Detail(note="x"),
        (sm.Detail(note="y"),),
    )
    assert (second.label, second.detail, second.details) == ("b", None, ())


def test_a_materialized_value_object_names_exactly_what_storage_held() -> None:
    # `Customer.address` mirrors models/customer.yaml: a top-level One holding a
    # nested One (`geo`) and a nested Many (`phones`). Storage here omits `geo`
    # entirely, and the one phone element it holds omits `type`. Both read back as
    # their absence form AND stay unnamed, at both depths — which is what lets an
    # edit that authors an explicit `geo` differ from what was read, and lets
    # `phones` be carried through re-serialization without gaining a `type` key
    # storage never held.
    fixture = GraphFixture(vo_models.CUSTOMER_MODEL)
    customer = fixture.node(
        "Customer",
        {
            "id": 1,
            "name": "Ada",
            "address": {"street": "Main St", "city": "Oslo", "phones": [{"number": "555-0100"}]},
        },
    )
    (root,) = fixture.materialize(customer)
    address = cast("Any", root).address
    assert address.geo is None
    assert address.model_fields_set == {"street", "city", "phones"}
    (phone,) = address.phones
    assert phone.type is None
    assert phone.model_fields_set == {"number"}


def test_a_null_many_cardinality_document_column_constructs_an_empty_tuple() -> None:
    fixture = GraphFixture(_ORDERS)
    status = fixture.node(
        "SnapOrderStatus",
        {
            "id": 2,
            "order_id": 1,
            "order_item_id": None,
            "code": "empty",
            "primary_tag": None,
            "tags": None,
        },
    )
    (root,) = fixture.materialize(status)
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.tags == ()


# --------------------------------------------------------------------------- #
# A model / class disagreement about a member's SHAPE.                          #
#                                                                              #
# A class-backed model compiles its Metamodel FROM the classes, so the two     #
# agree by construction there — but they are two independent sources in the    #
# conformance lane, where the model is authored YAML and the class is a        #
# hand-written mirror. A model that calls a member a value object while the    #
# composed class maps it as a scalar has no Value Object class to construct,   #
# and construction must say so rather than hand back a decoded record typed as #
# the declared member (spec §3's instances-only contract).                     #
# --------------------------------------------------------------------------- #
class _MergeScalarProfile(
    Entity, table="merge_scalar_profile", name="MergeScalarProfile", namespace=_NAMESPACE
):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[str] = attr(max_length=32)


_SCALAR_PROFILE = DomainModel(_MergeScalarProfile)


class _MergeDocumentProfile(ValueObject):
    note: Attr[str]


class _MergeVoProfile(
    Entity,
    table="merge_scalar_profile",
    name="MergeScalarProfile",
    namespace=_NAMESPACE,
):
    id: Attr[int] = attr(primary_key=True)
    profile: Attr[_MergeDocumentProfile]


_PROFILE_AS_VALUE_OBJECT = model_of(DomainModel(_MergeVoProfile))


def test_a_value_object_member_with_no_bound_class_is_refused() -> None:
    # The premise: the bound CLASS really does map `profile` as a scalar, so the
    # refusal below comes from the disagreement with the model above and not
    # from a malformed class declaration.
    assert [a.identity.name for a in _MergeScalarProfile.attributes] == ["id", "profile"]
    assert _MergeScalarProfile.value_objects == ()

    fixture = GraphFixture(_SCALAR_PROFILE, model=_PROFILE_AS_VALUE_OBJECT)
    node = fixture.node("MergeScalarProfile", {"id": 1, "profile": {"note": "x"}})
    with pytest.raises(GraphConstructionError) as refusal:
        fixture.materialize(node)
    assert refusal.value.code == "entity-graph-invalid-member"


# --------------------------------------------------------------------------- #
# Whole-graph pin and per-node edge.                                            #
# --------------------------------------------------------------------------- #
def test_a_temporal_node_carries_the_whole_graph_pin_and_its_own_edge() -> None:
    fixture = GraphFixture(read_models.BALANCE_MODEL)
    balance = fixture.node(
        "Balance",
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
    )
    pin = Pin(tx_time=dt.datetime(2024, 2, 1, tzinfo=dt.UTC))
    (root,) = fixture.materialize(balance, pin=pin)
    assert pin_of(root) is pin
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# A table-per-concrete-subtype family whose bitemporal axes are declared on the
# abstract ROOT and inherited by every concrete descendant (m-inheritance
# "Inherited members") — the corpus's own Rate/DepositRate shape
# (`models/rate.yaml`), where the concrete declares NO `asOfAttributes` locally.
class _MergeTemporalRoot(
    Bitemporal,
    name="MergeTemporalRoot",
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TABLE_PER_CONCRETE_SUBTYPE),
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


class _MergeTemporalLeaf(
    _MergeTemporalRoot,
    table="merge_temporal_leaf",
    name="MergeTemporalLeaf",
    namespace=_NAMESPACE,
    inheritance=ConcreteSubtype,
):
    grade: Attr[str | None] = attr(max_length=8)


_TEMPORAL_TPCS = DomainModel(_MergeTemporalRoot, _MergeTemporalLeaf)


def test_a_temporal_concrete_reads_its_edge_off_the_family_roots_own_axes() -> None:
    fixture = GraphFixture(_TEMPORAL_TPCS)
    leaf = fixture.node(
        "MergeTemporalLeaf",
        {
            "id": 1,
            "amount": Decimal("2.50"),
            "from_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "thru_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 6, 1, tzinfo=dt.UTC),
            "grade": "A",
        },
    )
    pin = Pin(
        valid_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        tx_time=dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
    )
    (root,) = fixture.materialize(leaf, pin=pin)
    assert isinstance(root, _MergeTemporalLeaf)
    assert pin_of(root) is pin
    assert edge_of(root).valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# The graph boundary: edges and roots are exact in-range projection indexes.   #
# --------------------------------------------------------------------------- #
_ORDER_IDENTITY = EntityIdentity(_NAMESPACE, "SnapOrder")
_ITEMS = RelationshipViewKey(RelationshipIdentity(_ORDER_IDENTITY, "items"))


class _Ordinal(IntEnum):
    FIRST = 0


def _one_projection() -> tuple[GraphBuilder, int]:
    """One builder holding exactly one projection, so ``1`` is out of range."""
    fixture = GraphFixture(_ORDERS)
    return fixture.builder, fixture.node("SnapOrder", _ORDER_ROW)


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(True, id="a-bool-is-not-an-exact-int"),
        pytest.param("0", id="a-string-is-not-an-int"),
        pytest.param(_Ordinal.FIRST, id="an-int-subclass-is-not-an-exact-int"),
    ],
)
def test_an_edge_that_is_not_an_exact_int_is_refused_where_it_is_written(value: object) -> None:
    builder, order = _one_projection()
    with pytest.raises(ValueError, match="exact built-in int"):
        builder.write_view(order, _ITEMS, value)


@pytest.mark.parametrize(
    "value",
    [pytest.param(-1, id="negative"), pytest.param(1, id="past-the-last-projection")],
)
def test_an_out_of_range_edge_is_refused_where_it_is_written(value: int) -> None:
    builder, order = _one_projection()
    with pytest.raises(ValueError, match="outside this graph's 1 projections"):
        builder.write_view(order, _ITEMS, value)


def test_a_to_many_edge_is_refused_element_by_element() -> None:
    builder, order = _one_projection()
    with pytest.raises(ValueError, match="a to-many relationship view names projection 4"):
        builder.write_view(order, _ITEMS, (0, 4))


def test_a_root_outside_the_graph_is_refused_at_sealing() -> None:
    builder, _ = _one_projection()
    with pytest.raises(ValueError, match="a root names projection 3"):
        builder.seal((3,), Pin())


def test_a_sealed_builder_refuses_every_further_use() -> None:
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    builder = fixture.builder
    builder.seal((order,), Pin())
    for use in (
        lambda: builder.write_view(order, _ITEMS, None),
        lambda: builder.concrete_of(order),
        lambda: builder.seal((order,), Pin()),
    ):
        with pytest.raises(ValueError, match="sealed its arrays"):
            use()


def test_a_merge_refuses_a_builder_that_has_published_no_graph() -> None:
    builder, _ = _one_projection()
    with pytest.raises(TypeError, match="publishes no graph to read"):
        merge_graph_input(builder)  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- #
# The indexed merge answers by reference, never by composition.                #
# --------------------------------------------------------------------------- #
def test_every_merge_accessor_answers_the_identical_object_on_a_second_call() -> None:
    # The interface exists to remove per-node composition, so equality would
    # pass over exactly the defect it forbids: two equal answers built twice.
    # The whole-graph properties are held to the same rule as the per-node
    # reads, over a graph whose every one of them is nonempty — a merged node
    # with duplicate projections, a loaded to-many, and a keyless root.
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    first = fixture.node("SnapOrderItem", _ITEM_ROW)
    second = fixture.node("SnapOrderItem", {**_ITEM_ROW, "id": 12})
    duplicate = fixture.node("SnapOrder", _ORDER_ROW)
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (first, second))
    merge = merge_graph_input(fixture.graph(order, keyless, duplicate))

    assert merge.layout(0) is merge.layout(0)
    assert merge.member_values(0) is merge.member_values(0)
    assert merge.issues(0) is merge.issues(0)
    assert merge.view_layout(0) is merge.view_layout(0)
    assert merge.view(0, 0) is merge.view(0, 0)
    assert merge.view(0, 0) == (1, 2)

    assert merge.order is merge.order
    assert merge.roots is merge.roots
    assert merge.invalid_roots is merge.invalid_roots
    assert merge.roots == (0, None, 0)
    assert len(merge.order) == 3
    assert [record.ordinal for record in merge.invalid_roots] == [1]


def test_one_view_shape_is_shared_by_every_node_that_carries_it() -> None:
    # Two Orders reached one way carry one merged view layout, so the ordering
    # rule runs once per shape rather than once per node.
    fixture = GraphFixture(_ORDERS)
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2})
    fixture.attach(first, "parallax.compatibility.SnapOrder.items", ())
    fixture.attach(second, "parallax.compatibility.SnapOrder.items", ())
    merge = merge_graph_input(fixture.graph(first, second))
    assert merge.view_layout(0) is merge.view_layout(1)


def test_a_member_the_read_did_not_carry_reads_absent_rather_than_null() -> None:
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", {key: _ORDER_ROW[key] for key in ("id", "name")})
    merge = merge_graph_input(fixture.graph(order))
    layout = merge.layout(0)
    values = merge.member_values(0)
    assert values[layout.index_of[AttributeIdentity(_ORDER_IDENTITY, "name")]] == "Ada"
    assert values[layout.index_of[AttributeIdentity(_ORDER_IDENTITY, "sku")]] is ABSENT
    # A failed assertion over a row has to name the absence it found, so the
    # sentinel spells itself rather than an address.
    assert repr(ABSENT) == "ABSENT"


def test_two_unreadable_projections_of_one_row_never_merge_with_each_other() -> None:
    # An invalid key short-circuits identity entirely, so a second read of the
    # identical unreadable row is a second logical node rather than the same one
    # diagnosed twice — which is what keeps each physical finding attributable.
    fixture = GraphFixture(_ORDERS)
    unreadable = {**_ORDER_ROW, "id": None}
    first = fixture.node("SnapOrder", unreadable)
    second = fixture.node("SnapOrder", unreadable)
    readable = fixture.node("SnapOrder", _ORDER_ROW)
    again = fixture.node("SnapOrder", _ORDER_ROW)
    merge = merge_graph_input(fixture.graph(first, second, readable, again))
    # Both unreadable roots are invalid-root holes, and the two readable ones
    # collapse onto one allocation — so the graph allocated one node, not three.
    assert merge.roots == (None, None, 0, 0)
    assert len(merge.order) == 1
    assert [record.ordinal for record in merge.invalid_roots] == [0, 1]


def test_no_published_value_is_the_absent_sentinel() -> None:
    # ABSENT is this runtime's own spelling of a position a read did not carry,
    # and it is never a value: a consumer skips the position, so what publishes
    # is a member the value does not have rather than a member holding a marker.
    fixture = GraphFixture(_ORDERS)
    order = fixture.node("SnapOrder", {key: _ORDER_ROW[key] for key in ("id", "name")})
    (root,) = fixture.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert "sku" not in root.model_fields_set
    assert all(value is not ABSENT for value in vars(root).values())


def _sole_node(merge: Any, name: str) -> int:
    (index,) = [index for index, entity in enumerate(merge.order) if entity.name == name]
    return index
