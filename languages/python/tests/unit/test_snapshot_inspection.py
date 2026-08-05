"""The Snapshot-owned inspection surface (``parallax.snapshot._inspection``):
``is_view_loaded`` / ``view`` / ``pin_of`` / ``edge_of`` over graphs the wrap seam
materialized, plus the refusals that precede every other check.

The suite drives whole graphs rather than hand-attached state, because what these
operations require is exactly what a Snapshot read attaches and nothing else.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest
from _snapshot_wrap_support import wrap

from _support import snapshot_models as sm
from parallax.conformance import animal_owner, read_models
from parallax.core.entity import RelationshipPath, UnloadedRelationshipError
from parallax.core.op_algebra import PathSegment
from parallax.core.temporal_read import Pin
from parallax.snapshot import (
    SnapshotInspectionError,
    edge_of,
    is_view_loaded,
    pin_of,
    view,
)
from parallax.snapshot._inspection import SNAPSHOT_INSPECTION_CODES
from parallax.snapshot.materialize import Node

_ORDERS = sm.SNAP_ORDERS_MODEL
_ANIMAL = sm.ANIMAL_MODEL
_BALANCE = read_models.BALANCE_MODEL


def _order(**relationships: object) -> Node:
    return Node(
        fields={
            "id": 1,
            "name": "Ada",
            "sku": None,
            "qty": 1,
            "price": Decimal("1.00"),
            "active": True,
            "ordered_on": dt.date(2024, 1, 1),
        },
        pk_columns=("id",),
        relationships=dict(relationships),
    )


def _item(item_id: int, **relationships: object) -> Node:
    return Node(
        fields={
            "id": item_id,
            "order_id": 1,
            "sku": "x",
            "quantity": 1,
            "shipped_on": None,
        },
        pk_columns=("id",),
        relationships=dict(relationships),
    )


def _status(status_id: int) -> Node:
    return Node(
        fields={
            "id": status_id,
            "order_id": 1,
            "order_item_id": None,
            "code": "SHIPPED",
        },
        pk_columns=("id",),
    )


def _dog(dog_id: int = 1, name: str = "Rex") -> Node:
    return Node(
        fields={"id": dog_id, "name": name, "owner_id": 10, "license_id": None, "bark_volume": 7},
        pk_columns=("id",),
        resolved_entity=cast("Any", sm.Dog.identity),
    )


# --------------------------------------------------------------------------- #
# `snapshot-node-required` precedes every other question.                      #
# --------------------------------------------------------------------------- #


def _loaded(node: object) -> object:
    return is_view_loaded(node, sm.SnapOrder.items)


def _viewed(node: object) -> object:
    return view(node, sm.SnapOrder.items)


@pytest.mark.parametrize(
    ("operation", "call"),
    [
        ("is_view_loaded", _loaded),
        ("view", _viewed),
        ("pin_of", pin_of),
        ("edge_of", edge_of),
    ],
)
def test_every_operation_refuses_a_node_this_lifecycle_did_not_produce(
    operation: str, call: Callable[[object], object]
) -> None:
    plain = sm.SnapOrder(
        id=1,
        name="Ada",
        sku=None,
        qty=1,
        price=Decimal("1.00"),
        active=True,
        ordered_on=dt.date(2024, 1, 1),
    )
    with pytest.raises(SnapshotInspectionError) as refusal:
        call(plain)
    assert refusal.value.code == "snapshot-node-required"
    assert refusal.value.operation == operation


def test_the_lifecycle_refusal_precedes_the_owner_check() -> None:
    # The path's owner is unrelated to the object AND the object carries no
    # Snapshot state; the lifecycle refusal is the one that fires.
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(object(), sm.SnapOrder.items)
    assert refusal.value.code == "snapshot-node-required"


# --------------------------------------------------------------------------- #
# Owner application and the path-only argument rule.                           #
# --------------------------------------------------------------------------- #


def test_a_path_whose_owner_does_not_apply_raises_rather_than_answering_false() -> None:
    (root,) = wrap((_order(),), "SnapOrder", _ORDERS)
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(root, sm.AnimalOwner.pets)
    assert refusal.value.code == "snapshot-view-owner-mismatch"
    assert refusal.value.entity == sm.SnapOrder.identity


def test_a_bare_relationship_name_is_not_an_accepted_argument() -> None:
    (root,) = wrap((_order(),), "SnapOrder", _ORDERS)
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(root, cast("Any", "items"))
    assert refusal.value.code == "snapshot-view-owner-mismatch"


def test_a_relationship_an_ancestor_declares_applies_to_its_concrete_subtype() -> None:
    # `owner` is declared on the family root `Animal`; the node is a `Dog`, and
    # a subtype never redeclares an inherited relationship.
    dog = Node(
        fields={"id": 1, "name": "Rex", "owner_id": 10, "license_id": None, "bark_volume": 7},
        pk_columns=("id",),
        resolved_entity=cast("Any", read_models.Dog.identity),
    )
    (root,) = wrap((dog,), "Animal", animal_owner.ANIMAL_MODEL)
    assert type(root) is read_models.Dog
    assert is_view_loaded(root, read_models.Animal.owner) is False


# --------------------------------------------------------------------------- #
# Loaded state and traversal.                                                  #
# --------------------------------------------------------------------------- #


def test_a_loaded_view_answers_true_and_an_unrequested_one_answers_false() -> None:
    (root,) = wrap((_order(items=[_item(11)]),), "SnapOrder", _ORDERS)
    assert is_view_loaded(root, sm.SnapOrder.items) is True
    assert is_view_loaded(root, sm.SnapOrder.statuses) is False


def test_view_answers_the_loaded_value_and_raises_for_an_unloaded_one() -> None:
    (root,) = wrap((_order(items=[_item(11)]),), "SnapOrder", _ORDERS)
    items = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items))
    assert [item.id for item in items] == [11]
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.statuses)


def test_a_to_many_path_fans_out_into_one_flat_tuple_in_traversal_order() -> None:
    first = _item(11, statuses=[_status(21), _status(22)])
    second = _item(12, statuses=[_status(23)])
    (root,) = wrap((_order(items=[first, second]),), "SnapOrder", _ORDERS)
    reached = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items.statuses))
    assert [status.id for status in reached] == [21, 22, 23]


def test_an_empty_to_many_branch_contributes_no_terminal_and_stays_a_tuple() -> None:
    (root,) = wrap((_order(items=[]),), "SnapOrder", _ORDERS)
    assert view(root, sm.SnapOrder.items.statuses) == ()
    # The uninstantiated suffix of an empty branch is vacuously loaded.
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is True


def test_an_all_to_one_path_answers_its_terminal_or_none() -> None:
    root_order = _order()
    item = _item(11, order=root_order)
    root_order.relationships["items"] = [item]
    (root,) = wrap((root_order,), "SnapOrder", _ORDERS)
    reached = cast("Any", root).items[0]
    assert view(reached, sm.SnapOrderItem.order) is root

    orphan = _item(50, order=None)
    (lone,) = wrap((orphan,), "SnapOrderItem", _ORDERS)
    assert view(lone, sm.SnapOrderItem.order) is None


def test_an_unloaded_view_on_a_deeper_segment_is_the_one_reported() -> None:
    (root,) = wrap((_order(items=[_item(11)]),), "SnapOrder", _ORDERS)
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.items.statuses)


# --------------------------------------------------------------------------- #
# Narrowed views.                                                              #
# --------------------------------------------------------------------------- #


def test_a_narrowed_view_is_read_by_its_own_path_and_never_marks_the_broad_one() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    assert is_view_loaded(root, sm.AnimalOwner.pets) is False
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Dog)) is True
    reached = cast("tuple[Any, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    assert [type(pet) for pet in reached] == [sm.Dog]
    with pytest.raises(UnloadedRelationshipError, match=r"pets\[Cat\]"):
        view(root, sm.AnimalOwner.pets.narrow(sm.Cat))


def test_equivalent_narrow_spellings_name_one_view() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Cat,Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    directly = RelationshipPath[Any, Any](
        segments=(PathSegment(rel="AnimalOwner.pets", narrow=("Dog", "Cat")),), target=None
    )
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat, sm.Dog)) is True
    assert is_view_loaded(root, directly) is True


# --------------------------------------------------------------------------- #
# Pin and edge.                                                                #
# --------------------------------------------------------------------------- #


def _balance_node() -> Node:
    return Node(
        fields={
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        },
        pk_columns=("bal_id",),
    )


def test_a_temporal_node_answers_the_whole_graph_pin_and_its_own_edge() -> None:
    pin = Pin(tx_time=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))
    (root,) = wrap((_balance_node(),), "Balance", _BALANCE, pin=pin)
    assert pin_of(root) is pin
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_a_non_temporal_node_reports_its_missing_pin_and_edge_by_code() -> None:
    (root,) = wrap((_order(),), "SnapOrder", _ORDERS)
    with pytest.raises(SnapshotInspectionError) as no_pin:
        pin_of(root)
    assert no_pin.value.code == "snapshot-pin-unavailable"
    assert no_pin.value.entity == sm.SnapOrder.identity

    with pytest.raises(SnapshotInspectionError) as no_edge:
        edge_of(root)
    assert no_edge.value.code == "snapshot-edge-unavailable"
    assert no_edge.value.operation == "edge_of"


def test_an_unrequested_narrowed_view_answers_false_rather_than_raising() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "favorite_id": None},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat)) is False


def test_a_deeper_segment_whose_owner_does_not_apply_is_refused_mid_traversal() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "favorite_id": None},
        pk_columns=("id",),
        relationships={"animals": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    # `AnimalOwner.animals` reaches an `Animal`; continuing with a segment
    # spelled from an unrelated owner reaches nothing that declares it.
    path = RelationshipPath[Any, Any](
        segments=(
            PathSegment(rel="AnimalOwner.animals"),
            PathSegment(rel="SnapOrder.items"),
        ),
        target=None,
    )
    with pytest.raises(SnapshotInspectionError) as refusal:
        view(root, path)
    assert refusal.value.code == "snapshot-view-owner-mismatch"


def test_a_narrowed_to_one_view_answers_the_node_itself_or_loaded_null() -> None:
    # A to-one hop narrows exactly as a to-many one does, and its view value is
    # then a single node — or loaded-null — rather than a tuple.
    favorite = Node(
        fields={"id": 10, "name": "Alice", "favorite_id": 1},
        pk_columns=("id",),
        relationships={"favorite[Dog]": _dog()},
    )
    (root,) = wrap((favorite,), "AnimalOwner", _ANIMAL)
    assert type(view(root, sm.AnimalOwner.favorite.narrow(sm.Dog))) is sm.Dog

    empty = Node(
        fields={"id": 11, "name": "Bob", "favorite_id": None},
        pk_columns=("id",),
        relationships={"favorite[Dog]": None},
    )
    (bob,) = wrap((empty,), "AnimalOwner", _ANIMAL)
    assert is_view_loaded(bob, sm.AnimalOwner.favorite.narrow(sm.Dog)) is True
    assert view(bob, sm.AnimalOwner.favorite.narrow(sm.Dog)) is None


def test_the_inspection_code_set_is_closed_against_an_unlisted_code() -> None:
    assert {
        "snapshot-node-required",
        "snapshot-view-owner-mismatch",
        "snapshot-pin-unavailable",
        "snapshot-edge-unavailable",
    } == SNAPSHOT_INSPECTION_CODES
    with pytest.raises(ValueError, match="not a snapshot inspection code"):
        SnapshotInspectionError(
            code="snapshot-nosuch", message="invented", operation="is_view_loaded"
        )
