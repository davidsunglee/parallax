"""Frozen developer-surface node wrapping (COR-3 Phase 7 increment 6a; spec
§3/§4): ``parallax.snapshot.wrap.wrap_graph`` over hand-built neutral graphs
(the same ``materialize.Node`` vocabulary ``test_materialize.py`` builds),
``Snapshot[T]``'s arity accessors, and the closed-world load-state
introspection (``is_loaded`` / ``narrowed`` / ``UnloadedRelationshipError``).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from decimal import Decimal
from typing import cast

import pytest

import mirrored_models  # noqa: F401  # pyright: ignore[reportUnusedImport] - registers Balance
import snapshot_models as sm
from parallax.conformance import models
from parallax.core import is_loaded, narrowed
from parallax.core.descriptor import Entity as EntityDescriptor
from parallax.core.descriptor import Inheritance
from parallax.core.entity import metamodel
from parallax.core.entity.expressions import UnloadedRelationshipError
from parallax.core.temporal_read import Pin, edge_of, pin_of
from parallax.snapshot import wrap
from parallax.snapshot.handle import Execution, NoResultFound, Snapshot, TooManyResultsFound
from parallax.snapshot.materialize import Node

pytestmark = pytest.mark.unit

_ORDERS = metamodel([sm.SnapOrder, sm.SnapOrderItem, sm.SnapOrderStatus])
_ANIMAL = metamodel([sm.Animal, sm.Pet, sm.Dog, sm.Cat, sm.WildBoar, sm.AnimalOwner])
# A metamodel the corpus/database DOES declare a concrete "Iguana" family member
# for (a legitimate descriptor entity, resolvable through `family_root`), but
# for which no Python class was ever registered — the exact defensive scenario
# `wrap._wrap`'s own `LookupError` guards, distinct from `identity_key`'s
# unrelated (and differently-worded) `meta.entity(...)` `KeyError` for a name
# the METAMODEL itself does not know at all.
_ANIMAL_WITH_UNREGISTERED_CONCRETE = dataclasses.replace(
    _ANIMAL,
    entities=(
        *_ANIMAL.entities,
        EntityDescriptor(
            name="Iguana",
            namespace="parallax.compatibility",
            table="animal",
            mutability="transactional",
            inheritance=Inheritance(role="concrete-subtype", parent="Pet", tag_value="iguana"),
        ),
    ),
)
_BALANCE = models.load_models()["balance"]


def _order_root() -> Node:
    item = Node(
        fields={"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None},
        pk_columns=("id",),
    )
    order = Node(
        fields={
            "id": 1,
            "name": "Ada",
            "sku": "A",
            "qty": 1,
            "price": Decimal("1"),
            "active": True,
            "ordered_on": dt.date(2024, 1, 1),
            "items": [item],
        },
        pk_columns=("id",),
    )
    item.fields["order"] = order
    return order


def test_wrap_graph_produces_a_frozen_instance_of_the_registered_class() -> None:
    (root,) = wrap.wrap_graph((_order_root(),), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    assert root.id == 1
    assert root.name == "Ada"
    assert root.price == Decimal("1")


def test_included_to_many_relationship_is_a_tuple_of_wrapped_instances() -> None:
    (root,) = wrap.wrap_graph((_order_root(),), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    assert isinstance(root.items, tuple)
    assert len(root.items) == 1
    assert isinstance(root.items[0], sm.SnapOrderItem)
    assert root.items[0].id == 11


def test_back_reference_cycle_closes_on_the_same_wrapped_instance() -> None:
    (root,) = wrap.wrap_graph((_order_root(),), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    assert root.items[0].order is root  # graph-local identity, hard pointer


def test_unloaded_relationship_access_raises_naming_the_path() -> None:
    bare = Node(
        fields={
            "id": 2,
            "name": "Bare",
            "sku": None,
            "qty": 1,
            "price": Decimal("1"),
            "active": True,
            "ordered_on": dt.date(2024, 1, 1),
        },
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((bare,), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    assert is_loaded(root, "items") is False
    with pytest.raises(UnloadedRelationshipError, match="items"):
        _ = root.items


def test_loaded_to_one_relationship_is_the_node_or_none() -> None:
    (root,) = wrap.wrap_graph((_order_root(),), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    item = root.items[0]
    assert is_loaded(item, "order") is True
    assert item.order is root


def test_loaded_to_one_relationship_attached_as_none_wraps_to_none() -> None:
    orphan = Node(
        fields={
            "id": 50,
            "order_id": 1,
            "sku": "y",
            "quantity": 2,
            "shipped_on": None,
            "order": None,
        },
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((orphan,), "SnapOrderItem", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrderItem)
    assert is_loaded(root, "order") is True
    assert root.order is None


def test_loaded_empty_to_many_is_an_empty_tuple() -> None:
    parent = Node(
        fields={
            "id": 3,
            "name": "Empty",
            "sku": None,
            "qty": 1,
            "price": Decimal("1"),
            "active": True,
            "ordered_on": dt.date(2024, 1, 1),
            "items": [],
        },
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((parent,), "SnapOrder", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrder)
    assert root.items == ()
    assert is_loaded(root, "items") is True


# --------------------------------------------------------------------------- #
# Polymorphic wrapping (familyVariant) and narrowed views.                     #
# --------------------------------------------------------------------------- #
def _dog() -> Node:
    return Node(
        fields={
            "id": 1,
            "name": "Rex",
            "owner_id": 10,
            "license_id": "L-100",
            "bark_volume": 7,
            "familyVariant": "Dog",
        },
        pk_columns=("id",),
    )


def _cat() -> Node:
    return Node(
        fields={
            "id": 2,
            "name": "Tom",
            "owner_id": 10,
            "license_id": None,
            "indoor": True,
            "familyVariant": "Cat",
        },
        pk_columns=("id",),
    )


def test_polymorphic_children_materialize_as_their_concrete_classes() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "animals": [_dog(), _cat()]},
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((owner,), "AnimalOwner", _ANIMAL, Pin())
    assert isinstance(root, sm.AnimalOwner)
    dog, cat = root.animals
    assert type(dog) is sm.Dog
    assert type(cat) is sm.Cat
    assert dog.bark_volume == 7
    assert cat.indoor is True


def test_narrowed_view_is_independent_of_the_broad_relationship() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "pets[Dog]": [_dog()]},
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((owner,), "AnimalOwner", _ANIMAL, Pin())
    assert isinstance(root, sm.AnimalOwner)
    path = sm.AnimalOwner.pets.narrow(sm.Dog)
    assert is_loaded(root, "pets") is False
    assert is_loaded(root, sm.AnimalOwner.pets) is False  # an un-narrowed RelationshipPath
    assert is_loaded(root, "not_a_declared_relationship") is False  # no such py_name at all
    assert is_loaded(root, path) is True
    view = cast("tuple[object, ...]", narrowed(root, path))
    assert isinstance(view, tuple)
    assert type(view[0]) is sm.Dog
    with pytest.raises(UnloadedRelationshipError, match="pets"):
        _ = root.pets
    with pytest.raises(UnloadedRelationshipError):
        narrowed(root, sm.AnimalOwner.pets.narrow(sm.Cat))


def test_two_narrowed_views_coexist_independently_on_one_node() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "pets[Dog]": [_dog()], "pets[Cat]": [_cat()]},
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((owner,), "AnimalOwner", _ANIMAL, Pin())
    assert isinstance(root, sm.AnimalOwner)
    dogs = cast("tuple[object, ...]", narrowed(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    cats = cast("tuple[object, ...]", narrowed(root, sm.AnimalOwner.pets.narrow(sm.Cat)))
    assert type(dogs[0]) is sm.Dog
    assert type(cats[0]) is sm.Cat


def test_wrap_raises_lookup_error_for_an_unregistered_concrete_class() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice", "animals": [_dog(), _iguana()]},
        pk_columns=("id",),
    )
    with pytest.raises(LookupError, match="Iguana"):
        wrap.wrap_graph((owner,), "AnimalOwner", _ANIMAL_WITH_UNREGISTERED_CONCRETE, Pin())


def _iguana() -> Node:
    return Node(
        fields={"id": 3, "name": "Iggy", "owner_id": 10, "familyVariant": "Iguana"},
        pk_columns=("id",),
    )


# --------------------------------------------------------------------------- #
# Entity-level value-object members (cardinality one and many).                #
# --------------------------------------------------------------------------- #
def test_entity_level_value_object_members_wrap_into_their_declared_classes() -> None:
    status = Node(
        fields={
            "id": 1,
            "order_id": 1,
            "order_item_id": None,
            "code": "shipped",
            "primary_tag": None,
            "tags": [
                {
                    "label": "a",
                    "detail": {"note": "x"},
                    "details": [{"note": "y"}, None],
                },
                {"label": "b"},
                None,
            ],
        },
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((status,), "SnapOrderStatus", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.primary_tag is None
    assert len(root.tags) == 2
    first, second = root.tags
    assert isinstance(first, sm.Tag)
    assert first.label == "a"
    assert first.detail == sm.Detail(note="x")
    assert first.details == (sm.Detail(note="y"),)
    assert second.label == "b"
    assert second.detail is None
    assert second.details == ()


def test_a_null_cardinality_many_value_object_column_wraps_to_an_empty_tuple() -> None:
    empty_status = Node(
        fields={
            "id": 2,
            "order_id": 1,
            "order_item_id": None,
            "code": "empty",
            "primary_tag": None,
            "tags": None,
        },
        pk_columns=("id",),
    )
    (root,) = wrap.wrap_graph((empty_status,), "SnapOrderStatus", _ORDERS, Pin())
    assert isinstance(root, sm.SnapOrderStatus)
    assert root.tags == ()


# --------------------------------------------------------------------------- #
# Whole-graph pin / per-node edge attachment (temporal_read.pin_of / edge_of). #
# --------------------------------------------------------------------------- #
def test_temporal_node_carries_the_whole_graph_pin_and_its_own_edge() -> None:
    row = Node(
        fields={
            "id": 1,
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": dt.datetime(2024, 1, 1, tzinfo=dt.UTC),
            "out_z": dt.datetime(2024, 4, 1, tzinfo=dt.UTC),
        },
        pk_columns=("bal_id",),
    )
    pin = Pin(processing=dt.datetime(2024, 2, 1, tzinfo=dt.UTC))
    (root,) = wrap.wrap_graph((row,), "Balance", _BALANCE, pin)
    assert pin_of(root) is pin
    assert edge_of(root).processing == dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


# --------------------------------------------------------------------------- #
# Snapshot[T] arity accessors.                                                 #
# --------------------------------------------------------------------------- #
def _snapshot(roots: tuple[object, ...]) -> Snapshot[object]:
    return Snapshot(roots, Pin(), Execution(()))


def test_result_raises_on_zero_and_on_more_than_one() -> None:
    with pytest.raises(NoResultFound):
        _snapshot(()).result()
    with pytest.raises(TooManyResultsFound):
        _snapshot((1, 2)).result()
    assert _snapshot((1,)).result() == 1


def test_result_or_none_returns_none_on_zero_and_raises_on_more_than_one() -> None:
    assert _snapshot(()).result_or_none() is None
    assert _snapshot((1,)).result_or_none() == 1
    with pytest.raises(TooManyResultsFound):
        _snapshot((1, 2)).result_or_none()


def test_results_returns_a_fresh_list_per_call() -> None:
    snapshot = _snapshot((1, 2))
    first = snapshot.results()
    second = snapshot.results()
    assert first == [1, 2]
    assert first is not second


def test_snapshot_has_no_iteration_len_or_indexing() -> None:
    snapshot = _snapshot((1, 2))
    assert not hasattr(snapshot, "__iter__")
    assert not hasattr(snapshot, "__len__")
    assert not hasattr(snapshot, "__getitem__")


def test_snapshot_pin_and_execution_and_repr() -> None:
    pin = Pin(processing=dt.datetime(2024, 1, 1, tzinfo=dt.UTC))
    snapshot = Snapshot((1,), pin, Execution(()))
    assert snapshot.pin is pin
    assert snapshot.execution.round_trips == 0
    assert "Snapshot(roots=1" in repr(snapshot)
