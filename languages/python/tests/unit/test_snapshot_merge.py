"""Projection merging and Entity graph construction over Snapshot Graph Input.

Drives the production materializer end to end — merge, allocate, populate, and
the per-node state factory — over graph inputs built exactly as a read driver
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
from typing import Any, cast

import pytest
from _snapshot_graph_support import GraphBuilder

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
from parallax.core.metamodel import EntityIdentity, RelationshipIdentity
from parallax.core.op_algebra import PathSegment
from parallax.core.temporal_read import Pin
from parallax.snapshot import SnapshotInspectionError, edge_of, is_view_loaded, pin_of, view
from parallax.snapshot.materialize import (
    RelationshipViewKey,
    SnapshotGraphInput,
    SnapshotNodeInput,
    SnapshotNodeRef,
    SnapshotRelationshipViewInput,
    merge_graph_input,
)

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
    builder = GraphBuilder(_ORDERS)
    order = builder.node("SnapOrder", _ORDER_ROW)
    (root,) = builder.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert (root.id, root.name, root.price) == (1, "Ada", Decimal("1"))


def test_an_included_to_many_is_a_tuple_and_its_back_reference_closes_the_cycle() -> None:
    builder = GraphBuilder(_ORDERS)
    order = builder.node("SnapOrder", _ORDER_ROW)
    item = builder.node("SnapOrderItem", _ITEM_ROW)
    builder.attach(order, "parallax.compatibility.SnapOrder.items", (item,))
    builder.attach(item, "parallax.compatibility.SnapOrderItem.order", order)
    (root,) = builder.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert isinstance(root.items, tuple)
    assert root.items[0].id == 11
    assert root.items[0].order is root


def test_a_relationship_no_projection_carried_stays_unloaded() -> None:
    builder = GraphBuilder(_ORDERS)
    (root,) = builder.materialize(builder.node("SnapOrder", _ORDER_ROW))
    assert isinstance(root, sm.SnapOrder)
    assert is_view_loaded(root, sm.SnapOrder.items) is False


def test_loaded_null_and_loaded_empty_are_distinct_from_unloaded() -> None:
    builder = GraphBuilder(_ORDERS)
    order = builder.node("SnapOrder", _ORDER_ROW)
    item = builder.node("SnapOrderItem", _ITEM_ROW)
    builder.attach(order, "parallax.compatibility.SnapOrder.items", ())
    builder.attach(item, "parallax.compatibility.SnapOrderItem.order", None)
    root, orphan = builder.materialize(order, item)
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
    builder = GraphBuilder(_ORDERS)
    first = builder.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    second = builder.node("SnapOrder", {**_ORDER_ROW, "id": 2, "name": "Linus"})
    roots = cast("tuple[Any, ...]", builder.materialize(second, first))
    assert [root.id for root in roots] == [2, 1]


# --------------------------------------------------------------------------- #
# Diamond projection merge: two SIBLING include paths reach the SAME logical    #
# row through two DIFFERENT projections (a driver never dedupes across sibling  #
# levels — each attach position converts its own row). `Order`/`OrderItem`      #
# declare TWO sibling relationships over the same join (`items` /               #
# `itemsByShipDate`), the shape m-snapshot-read-001 itself exercises.           #
# --------------------------------------------------------------------------- #
def test_a_diamond_collapses_onto_one_instance_and_unions_the_views() -> None:
    builder = GraphBuilder(_STORY_ORDERS)
    order = builder.node("Order", _ORDER_ROW)
    via_items = builder.node("OrderItem", _ITEM_ROW)
    via_ship_date = builder.node("OrderItem", _ITEM_ROW)
    builder.attach(order, "parallax.compatibility.Order.items", (via_items,))
    builder.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))
    # Only the SECOND path loaded the back-reference: the union is what carries it.
    builder.attach(via_ship_date, "parallax.compatibility.OrderItem.order", order)
    (root,) = builder.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0] is root.items_by_ship_date[0]
    assert is_view_loaded(root.items[0], _soOrderItem.order) is True
    assert root.items[0].order is root


def test_a_view_both_projections_carried_wires_exactly_once() -> None:
    builder = GraphBuilder(_STORY_ORDERS)
    order = builder.node("Order", _ORDER_ROW)
    via_items = builder.node("OrderItem", _ITEM_ROW)
    via_ship_date = builder.node("OrderItem", _ITEM_ROW)
    builder.attach(order, "parallax.compatibility.Order.items", (via_items,))
    builder.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))
    builder.attach(via_items, "parallax.compatibility.OrderItem.order", order)
    builder.attach(via_ship_date, "parallax.compatibility.OrderItem.order", order)
    (root,) = builder.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0] is root.items_by_ship_date[0]
    assert root.items[0].order is root


def test_each_to_many_view_keeps_its_own_order_through_the_merge() -> None:
    # The diamond's two views are ordered differently by their own declared
    # `orderBy`, and both reach the same two logical rows. Merging shares one
    # instance per row, so a per-view order that survived only because the two
    # tuples happened to hold distinct objects would be indistinguishable from
    # one that did not — which is what a REVERSED sibling states.
    builder = GraphBuilder(_STORY_ORDERS)
    order = builder.node("Order", _ORDER_ROW)
    first_by_id = builder.node("OrderItem", {**_ITEM_ROW, "id": 12, "sku": "later"})
    second_by_id = builder.node("OrderItem", _ITEM_ROW)
    first_by_ship_date = builder.node("OrderItem", _ITEM_ROW)
    second_by_ship_date = builder.node("OrderItem", {**_ITEM_ROW, "id": 12, "sku": "later"})
    builder.attach(order, "parallax.compatibility.Order.items", (first_by_id, second_by_id))
    builder.attach(
        order,
        "parallax.compatibility.Order.itemsByShipDate",
        (first_by_ship_date, second_by_ship_date),
    )
    (root,) = builder.materialize(order)
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
    builder = GraphBuilder(_STORY_ORDERS)
    order = builder.node("Order", _ORDER_ROW)
    first = builder.node("OrderItem", _ITEM_ROW)
    second = builder.node("OrderItem", {**_ITEM_ROW, "sku": "y"})
    builder.attach(order, "parallax.compatibility.Order.items", (first,))
    builder.attach(order, "parallax.compatibility.Order.itemsByShipDate", (second,))
    (root,) = builder.materialize(order)
    assert isinstance(root, _soOrder)
    assert root.items[0].sku == "x"


# --------------------------------------------------------------------------- #
# Polymorphic concrete resolution and narrowed views.                          #
# --------------------------------------------------------------------------- #
def test_polymorphic_children_materialize_as_their_concrete_classes() -> None:
    builder = GraphBuilder(_ANIMAL)
    owner = builder.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = builder.node("Dog", _DOG_ROW)
    cat = builder.node("Cat", _CAT_ROW)
    builder.attach(owner, "parallax.compatibility.AnimalOwner.animals", (dog, cat))
    (root,) = builder.materialize(owner)
    assert isinstance(root, sm.AnimalOwner)
    reached_dog, reached_cat = root.animals
    assert (type(reached_dog), type(reached_cat)) == (sm.Dog, sm.Cat)
    assert cast("sm.Dog", reached_dog).bark_volume == 7
    assert cast("sm.Cat", reached_cat).indoor is True


def test_a_narrowed_view_is_independent_of_the_broad_relationship() -> None:
    builder = GraphBuilder(_ANIMAL)
    owner = builder.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = builder.node("Dog", _DOG_ROW)
    builder.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    (root,) = builder.materialize(owner)
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
    builder = GraphBuilder(_ANIMAL)
    owner = builder.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = builder.node("Dog", _DOG_ROW)
    cat = builder.node("Cat", _CAT_ROW)
    builder.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    builder.attach(owner, "parallax.compatibility.AnimalOwner.pets", (cat,), narrowed="pets[Cat]")
    (root,) = builder.materialize(owner)
    dogs = cast("tuple[object, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    cats = cast("tuple[object, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Cat)))
    assert (type(dogs[0]), type(cats[0])) == (sm.Dog, sm.Cat)


def test_every_authoring_route_to_one_narrowed_view_reaches_the_same_value() -> None:
    # A `RelationshipPath` is a frozen value carrying nothing but its segments,
    # its target spelling and its source, so a directly built path and a copy
    # each key the same view as the class-derived one.
    builder = GraphBuilder(_ANIMAL)
    owner = builder.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = builder.node("Dog", _DOG_ROW)
    builder.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed="pets[Dog]")
    (root,) = builder.materialize(owner)
    derived = sm.AnimalOwner.pets.narrow(sm.Dog)
    direct: RelationshipPath[sm.AnimalOwner, sm.Dog] = RelationshipPath(
        segments=(PathSegment(rel="parallax.compatibility.AnimalOwner.pets", narrow=("Dog",)),),
        target="Dog",
    )
    for path in (derived, direct):
        reached = cast("tuple[object, ...]", view(root, path))
        assert type(reached[0]) is sm.Dog


def test_a_narrowed_to_one_view_carries_a_single_node_or_loaded_null() -> None:
    builder = GraphBuilder(_ANIMAL)
    alice = builder.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": 1})
    bob = builder.node("AnimalOwner", {"id": 11, "name": "Bob", "favorite_id": None})
    dog = builder.node("Dog", _DOG_ROW)
    builder.attach(
        alice, "parallax.compatibility.AnimalOwner.favorite", dog, narrowed="favorite[Dog]"
    )
    builder.attach(
        bob, "parallax.compatibility.AnimalOwner.favorite", None, narrowed="favorite[Dog]"
    )
    first, second = builder.materialize(alice, bob)
    assert type(view(first, sm.AnimalOwner.favorite.narrow(sm.Dog))) is sm.Dog
    assert view(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is None


def test_a_table_per_concrete_subtype_row_materializes_its_resolved_concrete() -> None:
    # A table-per-concrete-subtype position resolving to exactly ONE concrete
    # emits no `familyVariant` at all (`m-sql`'s `_compile_tpcs_single`); the
    # concrete Entity the compiled read resolved is what still selects the class.
    builder = GraphBuilder(_DOCUMENT)
    invoice = builder.node(
        "Invoice",
        {
            "id": 1,
            "title": "Invoice-A",
            "folder_id": None,
            "currency": "USD",
            "amount_due": Decimal("120.00"),
        },
    )
    (root,) = builder.materialize(invoice)
    assert type(root) is read_models.Invoice
    assert root.amount_due == Decimal("120.00")


# --------------------------------------------------------------------------- #
# Value Object construction.                                                   #
# --------------------------------------------------------------------------- #
def test_entity_level_value_object_members_construct_into_their_declared_classes() -> None:
    builder = GraphBuilder(_ORDERS)
    status = builder.node(
        "SnapOrderStatus",
        {
            "id": 1,
            "order_id": 1,
            "order_item_id": None,
            "code": "shipped",
            "primary_tag": None,
            "tags": [
                {"label": "a", "detail": {"note": "x"}, "details": [{"note": "y"}, None]},
                {"label": "b"},
                None,
            ],
        },
    )
    (root,) = builder.materialize(status)
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
    builder = GraphBuilder(vo_models.CUSTOMER_MODEL)
    customer = builder.node(
        "Customer",
        {
            "id": 1,
            "name": "Ada",
            "address": {"street": "Main St", "city": "Oslo", "phones": [{"number": "555-0100"}]},
        },
    )
    (root,) = builder.materialize(customer)
    address = cast("Any", root).address
    assert address.geo is None
    assert address.model_fields_set == {"street", "city", "phones"}
    (phone,) = address.phones
    assert phone.type is None
    assert phone.model_fields_set == {"number"}


def test_a_null_many_cardinality_document_column_constructs_an_empty_tuple() -> None:
    builder = GraphBuilder(_ORDERS)
    status = builder.node(
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
    (root,) = builder.materialize(status)
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

    builder = GraphBuilder(_SCALAR_PROFILE, model=_PROFILE_AS_VALUE_OBJECT)
    node = builder.node("MergeScalarProfile", {"id": 1, "profile": {"note": "x"}})
    with pytest.raises(GraphConstructionError) as refusal:
        builder.materialize(node)
    assert refusal.value.code == "entity-graph-invalid-member"


# --------------------------------------------------------------------------- #
# Whole-graph pin and per-node edge.                                            #
# --------------------------------------------------------------------------- #
def test_a_temporal_node_carries_the_whole_graph_pin_and_its_own_edge() -> None:
    builder = GraphBuilder(read_models.BALANCE_MODEL)
    balance = builder.node(
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
    (root,) = builder.materialize(balance, pin=pin)
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
    builder = GraphBuilder(_TEMPORAL_TPCS)
    leaf = builder.node(
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
    (root,) = builder.materialize(leaf, pin=pin)
    assert isinstance(root, _MergeTemporalLeaf)
    assert pin_of(root) is pin
    assert edge_of(root).valid_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Graph-input validation, ahead of any merging.                                #
# --------------------------------------------------------------------------- #
_ORDER_IDENTITY = EntityIdentity(_NAMESPACE, "SnapOrder")
_ITEMS = RelationshipViewKey(RelationshipIdentity(_ORDER_IDENTITY, "items"))


def _graph(*nodes: SnapshotNodeInput) -> SnapshotGraphInput:
    return SnapshotGraphInput(nodes=nodes, roots=(SnapshotNodeRef(0),), pin=Pin())


def test_a_reference_outside_the_input_is_refused_before_merging() -> None:
    node = SnapshotNodeInput(
        concrete_entity=_ORDER_IDENTITY,
        relationship_views=(SnapshotRelationshipViewInput(_ITEMS, SnapshotNodeRef(7)),),
    )
    with pytest.raises(ValueError, match="outside this graph input"):
        merge_graph_input(_graph(node), model_of(_ORDERS))


def test_a_root_reference_outside_the_input_is_refused() -> None:
    graph = SnapshotGraphInput(nodes=(), roots=(SnapshotNodeRef(0),), pin=Pin())
    with pytest.raises(ValueError, match="a root references node index 0"):
        merge_graph_input(graph, model_of(_ORDERS))


def test_two_entries_for_one_view_within_a_node_are_refused() -> None:
    node = SnapshotNodeInput(
        concrete_entity=_ORDER_IDENTITY,
        relationship_views=(
            SnapshotRelationshipViewInput(_ITEMS, ()),
            SnapshotRelationshipViewInput(_ITEMS, ()),
        ),
    )
    with pytest.raises(ValueError, match="two relationship view entries"):
        merge_graph_input(_graph(node), model_of(_ORDERS))
