"""The second materializer: one merged graph as class-free nodes and views.

Drives the real seam rather than a stand-in — ``convert_row`` into a
``MergeScope``, ``merge_graph_input``, then ``neutral_graph`` — so what these
assert is what a neutral read publishes. The typed materializer runs over the
same builder in the graph suites, which is what makes "peers over one merge"
checkable rather than asserted.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from decimal import Decimal
from typing import cast

import pytest
from _snapshot_graph_support import GraphBuilder, identity_of

from _support import snapshot_models as sm
from _support import value_object_models as vom
from parallax.core.entity._model import model_of
from parallax.core.metamodel import AttributeIdentity, Metamodel, RelationshipIdentity
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey, ObservationKey
from parallax.snapshot.materialize import (
    NeutralGraph,
    NeutralNodeView,
    ObservationKeying,
    RelationshipViewKey,
    SnapshotNodeRef,
    merge_graph_input,
    neutral_graph,
    neutral_rows,
)

CUSTOMER = model_of(vom.CUSTOMER_MODEL)
ORDERS = model_of(sm.SNAP_ORDERS_MODEL)
ANIMALS = model_of(sm.ANIMAL_MODEL)


_NO_PIN = Pin()


def _neutral(
    builder: GraphBuilder,
    *roots: SnapshotNodeRef,
    model: Metamodel,
    pin: Pin = _NO_PIN,
    observed: ObservationKeying | None = None,
) -> NeutralGraph:
    graph = builder.graph(*roots, pin=pin)
    return neutral_graph(merge_graph_input(graph, model), model, observed=observed)


def _members(view: NeutralNodeView, occurrence: str) -> Mapping[str, object]:
    """One top-level occurrence's filled members, by declared name."""
    for identity, value in view.value_objects.items():
        if identity.path[-1] == occurrence:
            assert isinstance(value, Mapping)
            return value
    raise AssertionError(f"no occurrence {occurrence!r} on {view.node.entity.canonical}")


def _view(view: NeutralNodeView, owner: str, name: str) -> object:
    for key, value in view.relationships.items():
        if key.relationship.name == name and key.relationship.source_entity.name == owner:
            return value
    raise AssertionError(f"no loaded view {owner}.{name}")


# --------------------------------------------------------------------------- #
# Declared-member fill: every declared member reads back, absence included.    #
# --------------------------------------------------------------------------- #


def test_a_stored_document_reads_back_every_declared_member() -> None:
    builder = GraphBuilder(vom.CUSTOMER_MODEL)
    root = builder.node(
        "Customer",
        {
            "id": 1,
            "name": "Ada",
            "address": {
                "street": "1 Park Ave",
                "city": "Oslo",
                "geo": {"country": "NO", "elevation": 10.5, "point": {"lat": 59.9, "lon": 10.7}},
                "phones": [{"type": "home", "number": "555-1234"}],
            },
        },
    )
    graph = _neutral(builder, root, model=CUSTOMER)
    address = _members(graph.roots[0], "address")
    assert address["street"] == "1 Park Ave"
    assert address["city"] == "Oslo"
    geo = cast("Mapping[str, object]", address["geo"])
    assert geo["country"] == "NO"
    assert cast("Mapping[str, object]", geo["point"])["lat"] == 59.9
    phones = cast("tuple[Mapping[str, object], ...]", address["phones"])
    assert [phone["number"] for phone in phones] == ["555-1234"]


def test_an_omitted_leaf_reads_null_rather_than_disappearing() -> None:
    """Required omissions are classified and no neutral graph is published."""
    builder = GraphBuilder(vom.CUSTOMER_MODEL)
    root = builder.node(
        "Customer", {"id": 5, "name": "Kavi", "address": {"street": "5 Harbour Rd", "geo": {}}}
    )
    with pytest.raises(ValueError, match="invalid stored data"):
        _neutral(builder, root, model=CUSTOMER)


def test_an_absent_many_occurrence_reads_empty_and_an_absent_one_reads_null() -> None:
    """A required top-level leaf omission refuses the whole neutral root."""
    builder = GraphBuilder(vom.CUSTOMER_MODEL)
    root = builder.node(
        "Customer", {"id": 6, "name": "Rin", "address": {"street": "6 Kastanien Allee"}}
    )
    with pytest.raises(ValueError, match="invalid stored data"):
        _neutral(builder, root, model=CUSTOMER)


def test_a_null_occurrence_stays_null_rather_than_becoming_a_filled_shell() -> None:
    """The fill is INSIDE an occurrence: a whole composite the row stored as NULL
    is absent, not a mapping of nulls (m-value-object-023's Customer 4)."""
    builder = GraphBuilder(vom.CUSTOMER_MODEL)
    root = builder.node("Customer", {"id": 4, "name": "Mary", "address": None})
    graph = _neutral(builder, root, model=CUSTOMER)
    assert next(iter(graph.roots[0].value_objects.values())) is None


def test_an_undeclared_stored_key_never_reaches_the_projection() -> None:
    builder = GraphBuilder(vom.CUSTOMER_MODEL)
    root = builder.node(
        "Customer", {"id": 1, "name": "Ada", "address": {"street": "x", "city": "y", "zip": "0"}}
    )
    assert "zip" not in _members(_neutral(builder, root, model=CUSTOMER).roots[0], "address")


# --------------------------------------------------------------------------- #
# Shared identity: diamonds and cycles.                                        #
# --------------------------------------------------------------------------- #


def test_a_diamond_reaches_one_shared_node_and_one_shared_view() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    order = builder.node("SnapOrder", _order_row(1))
    item = builder.node("SnapOrderItem", _item_row(10, order_id=1))
    status_left = builder.node("SnapOrderStatus", _status_row(100, order_id=1, item_id=10))
    status_right = builder.node("SnapOrderStatus", _status_row(101, order_id=1, item_id=10))
    builder.attach(order, "SnapOrder.items", (item,))
    builder.attach(order, "SnapOrder.statuses", (status_left, status_right))
    builder.attach(item, "SnapOrderItem.statuses", (status_left, status_right))
    graph = _neutral(builder, order, model=ORDERS)
    root = graph.roots[0]
    through_order = cast("tuple[NeutralNodeView, ...]", _view(root, "SnapOrder", "statuses"))
    items = cast("tuple[NeutralNodeView, ...]", _view(root, "SnapOrder", "items"))
    through_item = cast("tuple[NeutralNodeView, ...]", _view(items[0], "SnapOrderItem", "statuses"))
    assert through_order[0] is through_item[0]
    assert through_order[0].node is through_item[0].node


def test_a_back_reference_cycle_closes_on_the_view_already_built() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    order = builder.node("SnapOrder", _order_row(1))
    item = builder.node("SnapOrderItem", _item_row(10, order_id=1))
    builder.attach(order, "SnapOrder.items", (item,))
    builder.attach(item, "SnapOrderItem.order", order)
    root = _neutral(builder, order, model=ORDERS).roots[0]
    items = cast("tuple[NeutralNodeView, ...]", _view(root, "SnapOrder", "items"))
    assert _view(items[0], "SnapOrderItem", "order") is root


def test_two_projections_of_one_row_merge_onto_one_node() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    first = builder.node("SnapOrder", _order_row(1))
    second = builder.node("SnapOrder", _order_row(1))
    graph = _neutral(builder, first, second, model=ORDERS)
    assert graph.roots[0] is graph.roots[1]


# --------------------------------------------------------------------------- #
# Relationship state.                                                          #
# --------------------------------------------------------------------------- #


def test_the_four_relationship_states_stay_distinguishable() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    order = builder.node("SnapOrder", _order_row(1))
    item = builder.node("SnapOrderItem", _item_row(10, order_id=1))
    builder.attach(order, "SnapOrder.items", (item,))
    builder.attach(item, "SnapOrderItem.order", None)
    builder.attach(item, "SnapOrderItem.statuses", ())
    root = _neutral(builder, order, model=ORDERS).roots[0]
    loaded_item = cast("tuple[NeutralNodeView, ...]", _view(root, "SnapOrder", "items"))[0]
    assert isinstance(_view(root, "SnapOrder", "items"), tuple)
    assert _view(loaded_item, "SnapOrderItem", "order") is None
    assert _view(loaded_item, "SnapOrderItem", "statuses") == ()
    unloaded = RelationshipViewKey(
        RelationshipIdentity(identity_of(ORDERS, "SnapOrder"), "statuses")
    )
    assert unloaded not in root.relationships


def test_a_published_view_hands_out_no_mutable_relationship_map() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    order = builder.node("SnapOrder", _order_row(1))
    item = builder.node("SnapOrderItem", _item_row(10, order_id=1))
    builder.attach(order, "SnapOrder.items", (item,))
    root = _neutral(builder, order, model=ORDERS).roots[0]
    key = next(iter(root.relationships))
    with pytest.raises(TypeError):
        cast("dict[RelationshipViewKey, object]", root.relationships)[key] = None


def test_a_narrowed_view_and_its_broad_sibling_are_two_keys() -> None:
    builder = GraphBuilder(sm.ANIMAL_MODEL)
    owner = builder.node("AnimalOwner", {"id": 1, "name": "Ada", "favorite_id": None})
    dog = builder.node("Dog", _animal_row(10, "dog", owner_id=1))
    builder.attach(owner, "AnimalOwner.animals", (dog,))
    builder.attach(owner, "AnimalOwner.animals", (dog,), narrowed="animals[Dog]")
    root = _neutral(builder, owner, model=ANIMALS).roots[0]
    narrowed = [key for key in root.relationships if key.narrowed_view == "animals[Dog]"]
    broad = [
        key
        for key in root.relationships
        if key.relationship.name == "animals" and key.narrowed_view is None
    ]
    assert len(narrowed) == 1
    assert len(broad) == 1


# --------------------------------------------------------------------------- #
# Identity anchor, family variant, pin.                                        #
# --------------------------------------------------------------------------- #


def test_a_node_anchors_its_own_concrete_entity_and_family_declared_key() -> None:
    builder = GraphBuilder(sm.ANIMAL_MODEL)
    dog = builder.node("Dog", _animal_row(10, "dog", owner_id=None))
    root = _neutral(builder, dog, model=ANIMALS).roots[0]
    assert root.node.entity == identity_of(ANIMALS, "Dog")
    assert root.node.object_key == ObjectKey(identity_of(ANIMALS, "Dog"), (("id", 10),))
    assert root.primary_key == (AttributeIdentity(identity_of(ANIMALS, "Animal"), "id"),)
    assert root.family_variant == "Dog"


def test_a_standalone_entity_carries_no_family_variant() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    root = _neutral(builder, builder.node("SnapOrder", _order_row(1)), model=ORDERS).roots[0]
    assert root.family_variant is None


def test_the_graph_carries_the_pin_every_node_was_read_at() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    pin = Pin(tx_time=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    graph = _neutral(builder, builder.node("SnapOrder", _order_row(1)), model=ORDERS, pin=pin)
    assert graph.pin == pin


# --------------------------------------------------------------------------- #
# Observation keys.                                                            #
# --------------------------------------------------------------------------- #


def test_a_node_carries_no_observation_key_when_the_caller_supplies_no_rule() -> None:
    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    root = _neutral(builder, builder.node("SnapOrder", _order_row(1)), model=ORDERS).roots[0]
    assert root.node.observation_key is None


def test_the_keying_rule_is_asked_with_the_anchor_this_node_already_derived() -> None:
    seen: list[tuple[ObjectKey, Mapping[AttributeIdentity, object]]] = []

    def keying(
        object_key: ObjectKey, members: Mapping[AttributeIdentity, object]
    ) -> ObservationKey | None:
        seen.append((object_key, members))
        return ObservationKey(object_key, None)

    builder = GraphBuilder(sm.SNAP_ORDERS_MODEL)
    root = _neutral(
        builder, builder.node("SnapOrder", _order_row(1)), model=ORDERS, observed=keying
    ).roots[0]
    assert len(seen) == 1
    assert seen[0][0] is root.node.object_key
    assert root.node.observation_key == ObservationKey(root.node.object_key, None)


# --------------------------------------------------------------------------- #
# Row form.                                                                    #
# --------------------------------------------------------------------------- #


def test_row_form_detaches_each_row_from_the_mapping_it_was_built_from() -> None:
    source = {"id": 1, "name": "Ada"}
    rows = neutral_rows([source])
    source["name"] = "edited"
    assert list(rows) == [{"id": 1, "name": "Ada"}]
    assert len(rows) == 1
    with pytest.raises(TypeError):
        rows.rows[0]["name"] = "no"  # pyright: ignore[reportIndexIssue] - immutability is the point


# --------------------------------------------------------------------------- #
# Rows the builder converts.                                                   #
# --------------------------------------------------------------------------- #


def _order_row(order_id: int) -> dict[str, object]:
    return {
        "id": order_id,
        "name": "order",
        "sku": None,
        "qty": 1,
        "price": Decimal("1"),
        "active": True,
        "ordered_on": dt.date(2024, 1, 1),
    }


def _item_row(item_id: int, *, order_id: int) -> dict[str, object]:
    return {
        "id": item_id,
        "order_id": order_id,
        "sku": "s",
        "quantity": 1,
        "shipped_on": None,
    }


def _status_row(status_id: int, *, order_id: int, item_id: int) -> dict[str, object]:
    return {
        "id": status_id,
        "order_id": order_id,
        "order_item_id": item_id,
        "code": "ok",
        "primary_tag": None,
        "tags": None,
    }


def _animal_row(animal_id: int, kind: str, *, owner_id: int | None) -> dict[str, object]:
    return {
        "id": animal_id,
        "name": "rex",
        "owner_id": owner_id,
        "kind": kind,
        "license_id": None,
        "bark_volume": None,
        "indoor": None,
        "tusk_length": None,
    }
