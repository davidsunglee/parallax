"""The Snapshot-owned inspection surface (``parallax.snapshot._inspection``):
``is_view_loaded`` / ``view`` / ``pin_of`` / ``edge_of`` over graphs the
materializer produced, plus the refusals that precede every other check.

The suite drives whole graphs rather than hand-attached state, because what these
operations require is exactly what a Snapshot read attaches and nothing else.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any, cast

import pytest
from _snapshot_graph_support import GraphFixture

from _support import snapshot_models as sm
from parallax.conformance import animal_owner, read_models
from parallax.core.entity import RelationshipPath, UnloadedRelationshipError
from parallax.core.object_query import IncludeSegment
from parallax.core.temporal_read import Pin
from parallax.snapshot import (
    SnapshotInspectionError,
    edge_of,
    is_view_loaded,
    pin_of,
    view,
)
from parallax.snapshot._inspection import SNAPSHOT_INSPECTION_CODES

_ORDERS = sm.SNAP_ORDERS_MODEL
_ANIMAL = sm.ANIMAL_MODEL
_BALANCE = read_models.BALANCE_MODEL

_ORDER_ROW: dict[str, object] = {
    "id": 1,
    "name": "Ada",
    "sku": None,
    "qty": 1,
    "price": Decimal("1.00"),
    "active": True,
    "ordered_on": dt.date(2024, 1, 1),
}
_DOG_ROW: dict[str, object] = {
    "id": 1,
    "name": "Rex",
    "owner_id": 10,
    "license_id": None,
    "bark_volume": 7,
}
_OWNER_ROW: dict[str, object] = {"id": 10, "name": "Alice", "favorite_id": None}


def _item_row(item_id: int) -> dict[str, object]:
    return {"id": item_id, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None}


def _status_row(status_id: int) -> dict[str, object]:
    return {
        "id": status_id,
        "order_id": 1,
        "order_item_id": None,
        "code": "SHIPPED",
        "primary_tag": None,
        "tags": None,
    }


def _order_graph(*, items: tuple[dict[str, object], ...] | None = None) -> Any:
    """One `SnapOrder` root, optionally with a loaded `items` view."""
    fixture = GraphFixture(_ORDERS, "parallax.compatibility.SnapOrder.items")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    if items is not None:
        refs = tuple(fixture.node("SnapOrderItem", row) for row in items)
        fixture.attach(order, "parallax.compatibility.SnapOrder.items", refs)
    (root,) = fixture.materialize(order)
    return root


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
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(_order_graph(), sm.AnimalOwner.pets)
    assert refusal.value.code == "snapshot-view-owner-mismatch"
    assert refusal.value.entity == sm.SnapOrder.identity


def test_a_bare_relationship_name_is_not_an_accepted_argument() -> None:
    with pytest.raises(SnapshotInspectionError) as refusal:
        is_view_loaded(_order_graph(), cast("Any", "items"))
    assert refusal.value.code == "snapshot-view-owner-mismatch"


def test_a_relationship_an_ancestor_declares_applies_to_its_concrete_subtype() -> None:
    # `owner` is declared on the family root `Animal`; the node is a `Dog`, and
    # a subtype never redeclares an inherited relationship.
    fixture = GraphFixture(animal_owner.ANIMAL_MODEL)
    (root,) = fixture.materialize(fixture.node("Dog", _DOG_ROW))
    assert type(root) is read_models.Dog
    assert is_view_loaded(root, read_models.Animal.owner) is False


# --------------------------------------------------------------------------- #
# Loaded state and traversal.                                                  #
# --------------------------------------------------------------------------- #


def test_a_loaded_view_answers_true_and_an_unrequested_one_answers_false() -> None:
    root = _order_graph(items=(_item_row(11),))
    assert is_view_loaded(root, sm.SnapOrder.items) is True
    assert is_view_loaded(root, sm.SnapOrder.statuses) is False


def test_view_answers_the_loaded_value_and_raises_for_an_unloaded_one() -> None:
    root = _order_graph(items=(_item_row(11),))
    items = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items))
    assert [item.id for item in items] == [11]
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.statuses)


def test_a_to_many_path_fans_out_into_one_flat_tuple_in_traversal_order() -> None:
    fixture = GraphFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.statuses",
    )
    order = fixture.node("SnapOrder", _ORDER_ROW)
    first = fixture.node("SnapOrderItem", _item_row(11))
    second = fixture.node("SnapOrderItem", _item_row(12))
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (first, second))
    fixture.attach(
        first,
        "parallax.compatibility.SnapOrderItem.statuses",
        tuple(fixture.node("SnapOrderStatus", _status_row(status)) for status in (21, 22)),
    )
    fixture.attach(
        second,
        "parallax.compatibility.SnapOrderItem.statuses",
        (fixture.node("SnapOrderStatus", _status_row(23)),),
    )
    (root,) = fixture.materialize(order)
    reached = cast("tuple[Any, ...]", view(root, sm.SnapOrder.items.statuses))
    assert [status.id for status in reached] == [21, 22, 23]


def test_an_empty_to_many_branch_contributes_no_terminal_and_stays_a_tuple() -> None:
    root = _order_graph(items=())
    assert view(root, sm.SnapOrder.items.statuses) == ()
    # The uninstantiated suffix of an empty branch is vacuously loaded.
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is True


def test_an_all_to_one_path_answers_its_terminal_or_none() -> None:
    fixture = GraphFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.order",
    )
    order = fixture.node("SnapOrder", _ORDER_ROW)
    item = fixture.node("SnapOrderItem", _item_row(11))
    orphan = fixture.node("SnapOrderItem", _item_row(50))
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (item,))
    fixture.attach(item, "parallax.compatibility.SnapOrderItem.order", order)
    fixture.attach(orphan, "parallax.compatibility.SnapOrderItem.order", None)
    root, lone = fixture.materialize(order, orphan)
    assert view(cast("Any", root).items[0], sm.SnapOrderItem.order) is root
    assert view(lone, sm.SnapOrderItem.order) is None


def test_an_unloaded_view_on_a_deeper_segment_is_the_one_reported() -> None:
    root = _order_graph(items=(_item_row(11),))
    assert is_view_loaded(root, sm.SnapOrder.items.statuses) is False
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(root, sm.SnapOrder.items.statuses)


# --------------------------------------------------------------------------- #
# Narrowed views.                                                              #
# --------------------------------------------------------------------------- #


def _narrowed_owner(view_key: str, columns: dict[str, object] | None = None) -> Any:
    fixture = GraphFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.pets", view_key))
    owner = fixture.node("AnimalOwner", columns if columns is not None else _OWNER_ROW)
    dog = fixture.node("Dog", _DOG_ROW)
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.pets", (dog,), narrowed=view_key)
    (root,) = fixture.materialize(owner)
    return root


def test_a_narrowed_view_is_read_by_its_own_path_and_never_marks_the_broad_one() -> None:
    root = _narrowed_owner("pets[Dog]")
    assert is_view_loaded(root, sm.AnimalOwner.pets) is False
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Dog)) is True
    reached = cast("tuple[Any, ...]", view(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    assert [type(pet) for pet in reached] == [sm.Dog]
    with pytest.raises(UnloadedRelationshipError, match=r"pets\[Cat\]"):
        view(root, sm.AnimalOwner.pets.narrow(sm.Cat))


def test_equivalent_narrow_spellings_name_one_view() -> None:
    root = _narrowed_owner("pets[Cat,Dog]")
    directly = RelationshipPath[Any, Any](
        segments=(
            IncludeSegment(rel="parallax.compatibility.AnimalOwner.pets", narrow_to=("Dog", "Cat")),
        ),
        target=None,
    )
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat, sm.Dog)) is True
    assert is_view_loaded(root, directly) is True


def test_an_unrequested_narrowed_view_answers_false_rather_than_raising() -> None:
    root = _narrowed_owner("pets[Dog]")
    assert is_view_loaded(root, sm.AnimalOwner.pets.narrow(sm.Cat)) is False


def test_a_narrowed_to_one_view_answers_the_node_itself_or_loaded_null() -> None:
    # A to-one hop narrows exactly as a to-many one does, and its view value is
    # then a single node — or loaded-null — rather than a tuple.
    fixture = GraphFixture(
        _ANIMAL, ("parallax.compatibility.AnimalOwner.favorite", "favorite[Dog]")
    )
    alice = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": 1})
    bob = fixture.node("AnimalOwner", {"id": 11, "name": "Bob", "favorite_id": None})
    fixture.attach(
        alice,
        "parallax.compatibility.AnimalOwner.favorite",
        fixture.node("Dog", _DOG_ROW),
        narrowed="favorite[Dog]",
    )
    fixture.attach(
        bob, "parallax.compatibility.AnimalOwner.favorite", None, narrowed="favorite[Dog]"
    )
    first, second = fixture.materialize(alice, bob)
    assert type(view(first, sm.AnimalOwner.favorite.narrow(sm.Dog))) is sm.Dog
    assert is_view_loaded(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is True
    assert view(second, sm.AnimalOwner.favorite.narrow(sm.Dog)) is None


def test_a_deeper_segment_whose_owner_does_not_apply_is_refused_mid_traversal() -> None:
    fixture = GraphFixture(_ANIMAL, "parallax.compatibility.AnimalOwner.animals")
    owner = fixture.node("AnimalOwner", _OWNER_ROW)
    fixture.attach(
        owner, "parallax.compatibility.AnimalOwner.animals", (fixture.node("Dog", _DOG_ROW),)
    )
    (root,) = fixture.materialize(owner)
    # `AnimalOwner.animals` reaches an `Animal`; continuing with a segment
    # spelled from an unrelated owner reaches nothing that declares it.
    path = RelationshipPath[Any, Any](
        segments=(
            IncludeSegment(rel="parallax.compatibility.AnimalOwner.animals"),
            IncludeSegment(rel="parallax.compatibility.SnapOrder.items"),
        ),
        target=None,
    )
    with pytest.raises(SnapshotInspectionError) as refusal:
        view(root, path)
    assert refusal.value.code == "snapshot-view-owner-mismatch"


# --------------------------------------------------------------------------- #
# Pin and edge.                                                                #
# --------------------------------------------------------------------------- #


_MILESTONE_PIN = Pin(tx_time=dt.datetime(2024, 6, 1, tzinfo=dt.UTC))


def _balance_graph() -> Any:
    """One temporal `Balance` root materialized under a finite Transaction-Time
    pin, whose own milestone started earlier than the pin selects it at."""
    fixture = GraphFixture(_BALANCE)
    balance = fixture.node(
        "Balance",
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(9999, 12, 31, tzinfo=dt.UTC),
        },
    )
    (root,) = fixture.materialize(balance, pin=_MILESTONE_PIN)
    return root


def test_a_temporal_node_answers_the_whole_graph_pin_and_its_own_edge() -> None:
    root = _balance_graph()
    assert pin_of(root) is _MILESTONE_PIN
    assert edge_of(root).tx_time == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def test_a_non_temporal_node_reports_its_missing_pin_and_edge_by_code() -> None:
    root = _order_graph()
    with pytest.raises(SnapshotInspectionError) as no_pin:
        pin_of(root)
    assert no_pin.value.code == "snapshot-pin-unavailable"
    assert no_pin.value.entity == sm.SnapOrder.identity

    with pytest.raises(SnapshotInspectionError) as no_edge:
        edge_of(root)
    assert no_edge.value.code == "snapshot-edge-unavailable"
    assert no_edge.value.operation == "edge_of"


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


# --------------------------------------------------------------------------- #
# An Edited Copy. An edit replaces declared member state and preserves         #
# everything else, so the copy carries the very `SnapshotNodeState` its source  #
# node carries: every operation here answers for it, and answers the same.      #
# The carry itself is graded in `test_edit.py`; what it means to this surface   #
# is graded here.                                                              #
# --------------------------------------------------------------------------- #


def test_an_edited_copy_answers_every_view_question_as_its_source_node_did() -> None:
    root = _order_graph(items=(_item_row(11),))
    copy = root.edit(name="renamed")
    assert copy.name == "renamed"
    assert is_view_loaded(copy, sm.SnapOrder.items) is True
    assert is_view_loaded(copy, sm.SnapOrder.statuses) is False
    assert view(copy, sm.SnapOrder.items) == view(root, sm.SnapOrder.items)
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        view(copy, sm.SnapOrder.statuses)


def test_an_edited_copys_relationships_answer_through_ordinary_attribute_access() -> None:
    # The developer's own spelling, which is the one the closed world is stated
    # over: a loaded view is the value the read paid for, and an unloaded one is
    # a steered refusal naming the include fix — never a bare missing key.
    copy = _order_graph(items=(_item_row(11),)).edit(name="renamed")
    assert [item.id for item in copy.items] == [11]
    with pytest.raises(UnloadedRelationshipError, match="statuses"):
        copy.statuses  # noqa: B018 - the access itself is the assertion


def test_an_edited_copy_of_a_temporal_node_answers_the_same_pin_and_edge() -> None:
    # The pin travels with the copy, which is what makes a mutation derived from
    # a view pinned in the Transaction-Time past refusable at the verb.
    root = _balance_graph()
    copy = root.edit(value=Decimal("9.00"))
    assert pin_of(copy) is _MILESTONE_PIN
    assert edge_of(copy) is edge_of(root)
