"""Frozen developer-surface node identity and projection
(spec §3/§4): ``parallax.snapshot.handle._wrap.wrap_graph`` over hand-built
neutral graphs (the same ``materialize.Node`` vocabulary ``test_materialize.py``
builds), diamond projection and narrowed views, and the closed-world load-state
introspection (``is_loaded`` / ``narrowed`` / ``UnloadedRelationshipError``). The
value-object, temporal and ``Snapshot[T]`` half lives in
``test_snapshot_wrap_values.py``.
"""

from __future__ import annotations

import copy
import datetime as dt
from decimal import Decimal
from typing import cast

import pytest
from _snapshot_wrap_support import wrap

from _support import snapshot_models as sm
from parallax.conformance import read_models
from parallax.conformance.story_models import ORDERS_MODEL
from parallax.conformance.story_models import Order as _soOrder
from parallax.core import is_loaded, narrowed
from parallax.core.entity import RelationshipPath, UnloadedRelationshipError
from parallax.core.metamodel import EntityIdentity
from parallax.core.op_algebra import PathSegment
from parallax.snapshot.materialize import Node

_ORDERS = sm.SNAP_ORDERS_MODEL
_ANIMAL = sm.ANIMAL_MODEL
_DOCUMENT = read_models.DOCUMENT_MODEL


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
        },
        pk_columns=("id",),
        relationships={"items": [item]},
    )
    item.relationships["order"] = order
    return order


def test_wrap_graph_produces_a_frozen_instance_of_the_registered_class() -> None:
    (root,) = wrap((_order_root(),), "SnapOrder", _ORDERS)
    assert isinstance(root, sm.SnapOrder)
    assert root.id == 1
    assert root.name == "Ada"
    assert root.price == Decimal("1")


def test_included_to_many_relationship_is_a_tuple_of_wrapped_instances() -> None:
    (root,) = wrap((_order_root(),), "SnapOrder", _ORDERS)
    assert isinstance(root, sm.SnapOrder)
    assert isinstance(root.items, tuple)
    assert len(root.items) == 1
    assert isinstance(root.items[0], sm.SnapOrderItem)
    assert root.items[0].id == 11


def test_back_reference_cycle_closes_on_the_same_wrapped_instance() -> None:
    (root,) = wrap((_order_root(),), "SnapOrder", _ORDERS)
    assert isinstance(root, sm.SnapOrder)
    assert root.items[0].order is root  # graph-local identity, hard pointer


# --------------------------------------------------------------------------- #
# Diamond projection merge: two SIBLING include paths                          #
# reach the SAME logical row through two DIFFERENT `materialize.Node` objects  #
# (the assembler deliberately never dedupes across sibling levels — each       #
# attach position keeps its own freshly decoded `Node`, m-snapshot-read-012's  #
# own per-view wire contract). `Order`/`OrderItem` (from                      #
# ``parallax.conformance.story_models``) declare TWO sibling relationships     #
# over the same join (``items`` / ``itemsByShipDate``), the shape             #
# m-snapshot-read-001 itself exercises.                                        #
# --------------------------------------------------------------------------- #
_STORY_ORDERS = ORDERS_MODEL


def _diamond_order_asymmetric_include() -> Node:
    """Order 1, reached via ``items`` (no nested include) and ``itemsByShipDate``
    (which ALSO includes the ``order`` back-reference) — an asymmetric include
    over the SAME OrderItem row (id 11)."""
    item_via_items = Node(
        fields={"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None},
        pk_columns=("id",),
    )
    item_via_ship_date = Node(
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
        },
        pk_columns=("id",),
        relationships={
            "items": [item_via_items],
            "itemsByShipDate": [item_via_ship_date],
        },
    )
    item_via_ship_date.relationships["order"] = order
    return order


def test_diamond_projection_merges_a_relationship_loaded_on_only_one_sibling_path() -> None:
    (root,) = wrap((_diamond_order_asymmetric_include(),), "Order", _STORY_ORDERS)
    assert isinstance(root, _soOrder)
    # Both positions wrap to the SAME node (graph-local identity)…
    assert root.items[0] is root.items_by_ship_date[0]
    # …and the merged node carries the relationship EITHER path loaded — never
    # UNLOADED just because the FIRST-visited path (`items`) did not load it.
    assert is_loaded(root.items[0], "order") is True
    assert is_loaded(root.items_by_ship_date[0], "order") is True
    assert root.items[0].order is root
    assert root.items_by_ship_date[0].order is root


def _diamond_order_conflicting_include() -> Node:
    """Both ``items`` and ``itemsByShipDate`` load the SAME ``order`` back-
    reference on the SAME row (id 11) — the conflicting-view variant: the merge
    must wire the relationship exactly once, never raise, never double-wrap."""
    item_via_items = Node(
        fields={"id": 11, "order_id": 1, "sku": "x", "quantity": 1, "shipped_on": None},
        pk_columns=("id",),
    )
    item_via_ship_date = Node(
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
        },
        pk_columns=("id",),
        relationships={
            "items": [item_via_items],
            "itemsByShipDate": [item_via_ship_date],
        },
    )
    item_via_items.relationships["order"] = order
    item_via_ship_date.relationships["order"] = order
    return order


def test_diamond_projection_does_not_double_wire_a_relationship_loaded_on_both_paths() -> None:
    (root,) = wrap((_diamond_order_conflicting_include(),), "Order", _STORY_ORDERS)
    assert isinstance(root, _soOrder)
    assert root.items[0] is root.items_by_ship_date[0]
    assert is_loaded(root.items[0], "order") is True
    assert root.items[0].order is root


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
    (root,) = wrap((bare,), "SnapOrder", _ORDERS)
    assert isinstance(root, sm.SnapOrder)
    assert is_loaded(root, "items") is False
    with pytest.raises(UnloadedRelationshipError, match="items"):
        _ = root.items


def test_loaded_to_one_relationship_is_the_node_or_none() -> None:
    (root,) = wrap((_order_root(),), "SnapOrder", _ORDERS)
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
        },
        pk_columns=("id",),
        relationships={"order": None},
    )
    (root,) = wrap((orphan,), "SnapOrderItem", _ORDERS)
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
        },
        pk_columns=("id",),
        relationships={"items": []},
    )
    (root,) = wrap((parent,), "SnapOrder", _ORDERS)
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
        },
        pk_columns=("id",),
        resolved_entity=EntityIdentity("parallax.compatibility", "Dog"),
        family_variant="Dog",
    )


def _cat() -> Node:
    return Node(
        fields={
            "id": 2,
            "name": "Tom",
            "owner_id": 10,
            "license_id": None,
            "indoor": True,
        },
        pk_columns=("id",),
        resolved_entity=EntityIdentity("parallax.compatibility", "Cat"),
        family_variant="Cat",
    )


def test_polymorphic_children_materialize_as_their_concrete_classes() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"animals": [_dog(), _cat()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    assert isinstance(root, sm.AnimalOwner)
    dog, cat = root.animals
    assert type(dog) is sm.Dog
    assert type(cat) is sm.Cat
    assert dog.bark_volume == 7
    assert cat.indoor is True


def test_narrowed_view_is_independent_of_the_broad_relationship() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
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
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()], "pets[Cat]": [_cat()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    assert isinstance(root, sm.AnimalOwner)
    dogs = cast("tuple[object, ...]", narrowed(root, sm.AnimalOwner.pets.narrow(sm.Dog)))
    cats = cast("tuple[object, ...]", narrowed(root, sm.AnimalOwner.pets.narrow(sm.Cat)))
    assert type(dogs[0]) is sm.Dog
    assert type(cats[0]) is sm.Cat


# --------------------------------------------------------------------------- #
# A narrowed view is keyed by the path's own segments, and a `RelationshipPath`
# is a frozen value: a `copy` or `deepcopy` — each reconstructing the path from
# its own stored state rather than through `__init__` — keys the same view, and
# a deep copy shares the one Binding rather than minting a second identity for
# one hub. Pickling refuses, because hub identity deliberately cannot cross a
# wire.
# --------------------------------------------------------------------------- #
def test_a_directly_built_relationship_path_keys_the_same_narrowed_view() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    path = RelationshipPath(
        segments=(PathSegment(rel="AnimalOwner.pets", narrow=("Dog",)),), target="Dog"
    )
    assert is_loaded(root, path) is True
    view = cast("tuple[object, ...]", narrowed(root, path))
    assert type(view[0]) is sm.Dog


def test_narrowed_view_key_survives_copy_and_deepcopy_of_the_path() -> None:
    owner = Node(
        fields={"id": 10, "name": "Alice"},
        pk_columns=("id",),
        relationships={"pets[Dog]": [_dog()]},
    )
    (root,) = wrap((owner,), "AnimalOwner", _ANIMAL)
    path = sm.AnimalOwner.pets.narrow(sm.Dog)
    for reconstructed in (copy.copy(path), copy.deepcopy(path)):
        assert reconstructed == path
        assert is_loaded(root, reconstructed) is True
        view = cast("tuple[object, ...]", narrowed(root, reconstructed))
        assert len(view) == 1
        assert type(view[0]) is sm.Dog


# --------------------------------------------------------------------------- #
# A table-per-concrete-subtype                                                #
# ABSTRACT-position read narrowing (or naturally resolving) to exactly ONE    #
# concrete emits no `familyVariant` at all (`m-sql`'s `_compile_tpcs_single`) #
# — wrapping must still instantiate the resolved CONCRETE class, never the   #
# (possibly abstract) declared default.                                      #
# --------------------------------------------------------------------------- #
def test_wrap_a_single_resolved_position_node_instantiates_the_concrete_class() -> None:
    # `resolved_entity` is what the assembler threads through materialization
    # (`Assembler.materialize_root`'s own `narrow_to`) — this node carries no
    # `familyVariant` at all, mirroring the SQL `_compile_tpcs_single` emits.
    node = Node(
        fields={
            "id": 1,
            "title": "Invoice-A",
            "folder_id": None,
            "currency": "USD",
            "amount_due": Decimal("120.00"),
        },
        pk_columns=("id",),
        resolved_entity=EntityIdentity("parallax.compatibility", "Invoice"),
    )
    (root,) = wrap((node,), "FinancialDocument", _DOCUMENT)
    assert type(root) is read_models.Invoice
    assert root.amount_due == Decimal("120.00")


def test_wrap_without_resolved_entity_falls_back_to_the_declared_default() -> None:
    # The defensive-only shape: a hand-built `Node` that never went
    # through the assembler carries no `resolved_entity` at all, so wrapping
    # falls back to the caller's OWN declared default — unchanged behavior for
    # that defensive path, never reachable through `db.find` itself.
    node = Node(
        fields={
            "id": 1,
            "title": "Invoice-A",
            "folder_id": None,
            "currency": "USD",
            "amount_due": Decimal("120.00"),
        },
        pk_columns=("id",),
    )
    (root,) = wrap((node,), "Invoice", _DOCUMENT)
    assert type(root) is read_models.Invoice
