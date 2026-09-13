"""Root View judgment and Entity graph construction over a sealed Snapshot Page.

Drives the production materializer end to end — judge, allocate, populate, and
the per-node state factory — over Pages built exactly as a read driver
builds them: diamond collapse onto one instance, cycle closure by object
identity, narrowed views across every authoring route, loaded-null versus
loaded-empty versus unloaded, polymorphic concrete-class resolution, Value Object
construction, Page pin and per-node edge, and the Payload Witness /
view-union split the Root View is stated in.

Per-row conversion lives in `test_snapshot_conversion.py`; the inspection surface
these assertions read through has its own suite in `test_snapshot_inspection.py`.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from enum import IntEnum
from itertools import permutations
from typing import Any, cast

import pytest

from parallax.conformance import read_models, vo_models
from parallax.conformance.story_models import ORDERS_MODEL
from parallax.conformance.story_models import Order as _soOrder
from parallax.conformance.story_models import OrderItem as _soOrderItem
from parallax.core import (
    ONE_TO_MANY,
    TABLE_PER_CONCRETE_SUBTYPE,
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    DomainModel,
    Entity,
    Rel,
    TablePerHierarchy,
    ValueObject,
    attr,
    rel,
)
from parallax.core.entity import GraphConstructionError, RelationshipPath
from parallax.core.entity._model import model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    RelationshipIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)
from parallax.core.object_query import IncludeSegment
from parallax.core.temporal_read import Pin
from parallax.core.unit_work import ObjectKey
from parallax.snapshot import SnapshotInspectionError, edge_of, is_view_loaded, pin_of, view
from parallax.snapshot.materialize import (
    InvalidRootInput,
    RelationshipViewKey,
    RootView,
    SnapshotConsistencyError,
    StoredDataIssueInput,
    _convert,
)
from parallax.snapshot.materialize._page import ABSENT, PageBuilder, page_rows
from parallax.snapshot.materialize._publication import publication_issue
from parallax.snapshot.materialize._root import _member_order  # pyright: ignore[reportPrivateUsage]
from tests._support import snapshot_models as sm
from tests.unit.snapshot._snapshot_page_support import PageFixture, invalid_record

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


class ConflictAnimal(
    Entity,
    table="conflict_animal",
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    owner_id: Attr[int]


class ConflictAlpha(ConflictAnimal, inheritance=ConcreteSubtype(tag_value="alpha")):
    alpha: Attr[int | None]


class ConflictBeta(ConflictAnimal, inheritance=ConcreteSubtype(tag_value="beta")):
    beta: Attr[int | None]


class ConflictGamma(ConflictAnimal, inheritance=ConcreteSubtype(tag_value="gamma")):
    gamma: Attr[int | None]


class ConflictAnimalOwner(Entity, table="conflict_owner", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    animals: Rel[tuple[ConflictAnimal, ...]] = rel(cardinality=ONE_TO_MANY, join=("id", "owner_id"))


_CONFLICT_ANIMALS = DomainModel(
    ConflictAnimal, ConflictAlpha, ConflictBeta, ConflictGamma, ConflictAnimalOwner
)


# --------------------------------------------------------------------------- #
# Construction: frozen instances, closed-world arms, cycle closure.            #
# --------------------------------------------------------------------------- #
def test_a_resolved_node_becomes_a_frozen_instance_of_its_registered_class() -> None:
    fixture = PageFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    (root,) = fixture.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert (root.id, root.name, root.price) == (1, "Ada", Decimal("1"))


def test_an_included_to_many_is_a_tuple_and_its_back_reference_closes_the_cycle() -> None:
    fixture = PageFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.order",
    )
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
    fixture = PageFixture(_ORDERS)
    (root,) = fixture.materialize(fixture.node("SnapOrder", _ORDER_ROW))
    assert isinstance(root, sm.SnapOrder)
    assert is_view_loaded(root, sm.SnapOrder.items) is False


def test_loaded_null_and_loaded_empty_are_distinct_from_unloaded() -> None:
    fixture = PageFixture(
        _ORDERS,
        "parallax.compatibility.SnapOrder.items",
        "parallax.compatibility.SnapOrderItem.order",
    )
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
    # A multi-root Page states that Root View publication preserves the database
    # result order rather than projection insertion order.
    fixture = PageFixture(_ORDERS)
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2, "name": "Linus"})
    roots = cast("tuple[Any, ...]", fixture.materialize(second, first))
    assert [root.id for root in roots] == [2, 1]


def test_an_invalid_root_preserves_its_result_position_without_allocating_a_node() -> None:
    # The keyless row sits BETWEEN two valid ones, so the hole it leaves is a
    # result position rather than a truncation, and the two survivors keep the
    # allocation indices their own walk order gives them.
    fixture = PageFixture(_ORDERS)
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2, "name": "Linus"})

    root_view = RootView(fixture.page(first, keyless, second))
    assert root_view.roots == (0, None, 1)
    assert [issue.code for record in root_view.invalid_roots for issue in record.issues] == [
        "stored-data-primary-key-null"
    ]
    assert [record.ordinal for record in root_view.invalid_roots] == [1]
    assert root_view.order == (
        EntityIdentity(_NAMESPACE, "SnapOrder"),
        EntityIdentity(_NAMESPACE, "SnapOrder"),
    )


def test_publication_issue_reads_the_first_invalid_root_issue() -> None:
    fixture = PageFixture(_ORDERS)
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    root_view = RootView(fixture.page(keyless))
    assert publication_issue(root_view) is root_view.invalid_roots[0].issues[0]


def test_a_keyless_root_with_rejected_structured_evidence_dedupes_in_band() -> None:
    fixture = PageFixture(vo_models.CUSTOMER_MODEL)
    keyless = fixture.node(
        "Customer",
        {
            "id": None,
            "name": "Ada",
            "address": {"street": "1 Park Ave", "phones": {"type": "home"}},
        },
    )

    root = RootView(fixture.page(keyless))

    assert root.roots == (None,)
    assert [issue.code for issue in root.invalid_roots[0].issues] == [
        "stored-data-many-wrong-kind",
        "stored-data-primary-key-null",
    ]
    assert root.invalid_roots[0].issues[0].stored_value == {"type": "home"}


def test_invalid_root_carriers_require_a_position_and_an_issue() -> None:
    issue = StoredDataIssueInput(
        "stored-data-primary-key-null",
        EntityIdentity(_NAMESPACE, "SnapOrder"),
        stored_value=None,
    )
    with pytest.raises(ValueError, match="nonnegative"):
        InvalidRootInput(-1, (issue,))
    with pytest.raises(ValueError, match="at least one"):
        InvalidRootInput(0, ())


def test_an_invalid_root_ordinal_is_its_result_position_by_construction() -> None:
    # A caller never spells one: sealing derives the ordinal from the position
    # the root occupies, so the mismatch a whole-Page validation pass used to
    # look for is unrepresentable rather than checked.
    fixture = PageFixture(_ORDERS)
    valid = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    root_view = RootView(fixture.page(valid, keyless))
    assert [record.ordinal for record in root_view.invalid_roots] == [1]


# --------------------------------------------------------------------------- #
# Diamond projection judgment: two SIBLING include paths reach the SAME logical    #
# row through two DIFFERENT projections (a driver never dedupes across sibling  #
# levels — each attach position converts its own row). `Order`/`OrderItem`      #
# declare TWO sibling relationships over the same join (`items` /               #
# `itemsByShipDate`), the shape m-snapshot-read-001 itself exercises.           #
# --------------------------------------------------------------------------- #
def test_a_diamond_collapses_onto_one_instance_and_unions_the_views() -> None:
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
        "parallax.compatibility.OrderItem.order",
    )
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
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
        "parallax.compatibility.OrderItem.order",
    )
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


def test_each_to_many_view_keeps_its_own_order_through_the_root_view() -> None:
    # The diamond's two views are ordered differently by their own declared
    # `orderBy`, and both reach the same two logical rows. The Root View shares one
    # instance per row, so a per-view order that survived only because the two
    # tuples happened to hold distinct objects would be indistinguishable from
    # one that did not — which is what a REVERSED sibling states.
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
    )
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


def test_unequal_scalar_witnesses_refuse_before_any_payload_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    items = "parallax.compatibility.Order.items"
    by_ship_date = "parallax.compatibility.Order.itemsByShipDate"
    calls = 0
    decode = _convert._decode_row  # pyright: ignore[reportPrivateUsage]

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        return decode(*args, **kwargs)

    monkeypatch.setattr(_convert, "_decode_row", counting)

    def conflict(*views: str) -> SnapshotConsistencyError:
        fixture = PageFixture(_STORY_ORDERS, *views)
        order = fixture.node("Order", _ORDER_ROW)
        first = fixture.node("OrderItem", _ITEM_ROW)
        second = fixture.node("OrderItem", {**_ITEM_ROW, "sku": "y"})
        fixture.attach(order, items, (first,))
        fixture.attach(order, by_ship_date, (second,))
        page = fixture.page(order)
        with pytest.raises(SnapshotConsistencyError) as raised:
            RootView(page)
        assert page.judged_states == {}
        return raised.value

    forward = conflict(items, by_ship_date)
    reverse = conflict(by_ship_date, items)
    assert calls == 0
    assert forward.code == reverse.code == "snapshot-projection-conflict"
    assert forward.object_key == reverse.object_key
    assert forward.coordinates == reverse.coordinates
    assert forward.occurrences == reverse.occurrences
    assert (
        forward.members
        == reverse.members
        == (AttributeIdentity(EntityIdentity(_NAMESPACE, "OrderItem"), "sku"),)
    )


def test_three_unequal_occurrences_report_one_canonical_conflict() -> None:
    # Three provider occurrences of one child disagree along different member
    # sets. Every arrival permutation must select the same witness pair, differing
    # members, and canonical occurrence positions without exposing stored values.
    items = "parallax.compatibility.Order.items"
    rows = (
        _ITEM_ROW,
        {**_ITEM_ROW, "sku": "y"},
        {**_ITEM_ROW, "quantity": 9},
    )
    conflicts: list[SnapshotConsistencyError] = []
    for ordered in permutations(rows):
        fixture = PageFixture(_STORY_ORDERS, items)
        order = fixture.node("Order", _ORDER_ROW)
        children = tuple(fixture.node("OrderItem", row) for row in ordered)
        fixture.attach(order, items, children)
        with pytest.raises(SnapshotConsistencyError) as raised:
            RootView(fixture.page(order))
        conflicts.append(raised.value)

    first, *rest = conflicts
    assert all(
        (
            conflict.object_key,
            conflict.coordinates,
            conflict.members,
            conflict.occurrences,
        )
        == (first.object_key, first.coordinates, first.members, first.occurrences)
        for conflict in rest
    )
    assert str(first) == (
        "parallax.compatibility.OrderItem: projections disagree (snapshot-projection-conflict)"
    )


# Canonical conflict diagnostics order declared Attributes, Value Objects, and
# nested Value Object Attributes independently of set iteration, so every
# permutation reports one stable declared-member sequence.
def test_conflict_member_order_covers_every_declared_member_kind() -> None:
    entity = EntityIdentity(_NAMESPACE, "Customer")
    occurrence = ValueObjectIdentity(entity, ("address",))
    nested = ValueObjectAttributeIdentity(occurrence, "street")

    assert sorted((nested, occurrence, AttributeIdentity(entity, "name")), key=_member_order) == [
        AttributeIdentity(entity, "name"),
        occurrence,
        nested,
    ]


# Two concrete subtypes claiming one family key are a conflict even when arrival
# selects the later-sorting concrete first; the diagnostic reorders the pair by
# concrete identity before deriving its Object Key and differing members.
def test_concrete_disagreement_canonicalizes_the_diagnostic_entity() -> None:
    fixture = PageFixture(_ANIMAL, "parallax.compatibility.AnimalOwner.animals")
    owner = fixture.node("AnimalOwner", {"id": 10, "name": "Alice", "favorite_id": None})
    dog = fixture.node("Dog", _DOG_ROW)
    cat = fixture.node("Cat", {**_CAT_ROW, "id": 1})
    fixture.attach(owner, "parallax.compatibility.AnimalOwner.animals", (dog, cat))

    with pytest.raises(SnapshotConsistencyError) as raised:
        RootView(fixture.page(owner))

    assert raised.value.object_key.entity == EntityIdentity(_NAMESPACE, "Cat")


# Three supported concrete siblings carry value-identical positional witnesses
# under one family key. Reordering their source occurrences must still select the
# same concrete pair, Object Key Entity, differing-member sequence, and occurrence
# positions; otherwise source/include order leaks into the public conflict.
def test_three_concrete_disagreements_select_one_canonical_pair() -> None:
    relationship = "parallax.compatibility.ConflictAnimalOwner.animals"
    occurrences = (
        ("ConflictAlpha", {"id": 1, "owner_id": 10, "alpha": None}),
        ("ConflictBeta", {"id": 1, "owner_id": 10, "beta": None}),
        ("ConflictGamma", {"id": 1, "owner_id": 10, "gamma": None}),
    )
    conflicts: list[SnapshotConsistencyError] = []
    for ordered in permutations(occurrences):
        fixture = PageFixture(_CONFLICT_ANIMALS, relationship)
        owner = fixture.node("ConflictAnimalOwner", {"id": 10})
        children = tuple(fixture.node(entity, row) for entity, row in ordered)
        fixture.attach(owner, relationship, children)
        with pytest.raises(SnapshotConsistencyError) as raised:
            RootView(fixture.page(owner))
        conflicts.append(raised.value)

    first, *rest = conflicts
    assert all(
        (
            conflict.object_key,
            conflict.coordinates,
            conflict.members,
            conflict.occurrences,
        )
        == (first.object_key, first.coordinates, first.members, first.occurrences)
        for conflict in rest
    )
    assert first.object_key.entity.name == "ConflictAlpha"


def test_duplicate_projections_of_one_finding_retain_it_once() -> None:
    # Two sibling levels can project one invalid row twice, and each row is
    # judged and frozen before anything can know the two are one node. The
    # duplicate carries the first projection's issue record itself, so the node
    # holds one rejected value rather than an equal second for the Page's life,
    # and the Root View lists it once.
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
    )
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

    page = fixture.page(order)
    root = RootView(page)
    item = _sole_node(root, "OrderItem")
    assert [issue.code for issue in root.issues(item)] == ["stored-data-leaf-undecodable"]
    assert len(page.judged_states) == 2


def test_a_duplicate_projection_with_different_rejected_state_conflicts() -> None:
    # Sibling levels project different columns, so two projections of one node
    # may see different stored state. Sharing is what two equal judgments earn,
    # not what arriving second costs: a distinct rejected value is a distinct
    # fact about the stored row and both reach the same resolved node.
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
    )
    order = fixture.node("Order", _ORDER_ROW)
    via_items = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    via_ship_date = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "also-not-a-date"})
    fixture.attach(order, "parallax.compatibility.Order.items", (via_items,))
    fixture.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))

    with pytest.raises(SnapshotConsistencyError) as raised:
        RootView(fixture.page(order))
    assert raised.value.code == "snapshot-projection-conflict"


def test_exact_witness_comparison_distinguishes_bool_from_int() -> None:
    # Python considers True equal to 1, but the stored carriers are different
    # facts. Two projections reachable from one root must therefore conflict.
    fixture = PageFixture(
        _STORY_ORDERS,
        "parallax.compatibility.Order.items",
        "parallax.compatibility.Order.itemsByShipDate",
    )
    order = fixture.node("Order", _ORDER_ROW)
    via_items = fixture.node("OrderItem", {**_ITEM_ROW, "quantity": True})
    via_ship_date = fixture.node("OrderItem", {**_ITEM_ROW, "quantity": 1})
    fixture.attach(order, "parallax.compatibility.Order.items", (via_items,))
    fixture.attach(order, "parallax.compatibility.Order.itemsByShipDate", (via_ship_date,))

    with pytest.raises(SnapshotConsistencyError) as raised:
        RootView(fixture.page(order))
    assert raised.value.members == (
        AttributeIdentity(EntityIdentity(_NAMESPACE, "OrderItem"), "quantity"),
    )


def test_unequal_document_witnesses_in_separate_roots_coexist() -> None:
    # Two result roots may name one logical key at different stored states. They
    # are distinct root-local claims, so neither root imports evidence from the
    # other and both remain publishable verdicts.
    fixture = PageFixture(vo_models.CUSTOMER_MODEL)
    first = fixture.node("Customer", _customer_row("home"))
    second = fixture.node("Customer", _customer_row("work"))

    root_view = RootView(fixture.page(first, second))
    assert root_view.roots == (0, 1)
    assert len(root_view.order) == 2


def test_equal_witnesses_share_across_roots_but_unequal_witnesses_do_not() -> None:
    # Page-owned state sharing is earned by exact witness equality; root-local
    # conflict detection does not forbid another result root from carrying a
    # different state for the same logical key.
    fixture = PageFixture(vo_models.CUSTOMER_MODEL)
    clean = fixture.node(
        "Customer",
        {"id": 1, "name": "Ada", "address": {"street": "1 Park Ave", "phones": []}},
    )
    rejected = fixture.node("Customer", _customer_row("home"))
    rejected_again = fixture.node("Customer", _customer_row("home"))

    root_view = RootView(fixture.page(clean, rejected, rejected_again))
    assert root_view.roots == (0, 1, 1)
    assert len(root_view.order) == 2


def test_an_invalid_descendant_classifies_the_reachable_root() -> None:
    # Classification is root-granular: a clean root cannot hide an invalid
    # included child merely because the root's own members are constructible,
    # and the child's undecodable leaf leaves no value to hydrate the root from.
    fixture = PageFixture(_STORY_ORDERS, "parallax.compatibility.Order.items")
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
    fixture = PageFixture(_STORY_ORDERS)
    order = fixture.node("Order", _ORDER_ROW)
    fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})

    (root,) = fixture.materialize(order)
    assert isinstance(root, _soOrder)


def test_an_invalid_descendant_key_never_enters_logical_identity() -> None:
    # A child with no usable primary key remains a classified projection rather
    # than being shared under a synthetic `(None,)` logical key.
    fixture = PageFixture(_STORY_ORDERS, "parallax.compatibility.Order.items")
    order = fixture.node("Order", _ORDER_ROW)
    invalid = fixture.node("OrderItem", {**_ITEM_ROW, "id": None})
    fixture.attach(order, "parallax.compatibility.Order.items", (invalid,))

    root_view = RootView(fixture.page(order))
    item = _sole_node(root_view, "OrderItem")
    assert [issue.code for issue in root_view.issues(item)] == ["stored-data-primary-key-null"]
    published = invalid_record(fixture.materialize(order)[0])
    assert published.data is None
    # The child's own identity never decoded, so its diagnosis locates no object
    # while the root's record still locates the result position it invalidated.
    assert [issue.object_key for issue in published.issues] == [None]


# --------------------------------------------------------------------------- #
# Polymorphic concrete resolution and narrowed views.                          #
# --------------------------------------------------------------------------- #
def test_polymorphic_children_materialize_as_their_concrete_classes() -> None:
    fixture = PageFixture(_ANIMAL, "parallax.compatibility.AnimalOwner.animals")
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
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.pets", "pets[Dog]"))
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
    fixture = PageFixture(
        _ANIMAL,
        ("parallax.compatibility.AnimalOwner.pets", "pets[Dog]"),
        ("parallax.compatibility.AnimalOwner.pets", "pets[Cat]"),
    )
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
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.pets", "pets[Dog]"))
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
    fixture = PageFixture(_ANIMAL, ("parallax.compatibility.AnimalOwner.favorite", "favorite[Dog]"))
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
    fixture = PageFixture(_DOCUMENT)
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
    fixture = PageFixture(_ORDERS)
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
    fixture = PageFixture(vo_models.CUSTOMER_MODEL)
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
    fixture = PageFixture(_ORDERS)
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
#                                                                              #
# The member row the Page carries is laid out against the AUTHORED model and the     #
# writer reads it against the COMPOSED one, so what the two disagree about is  #
# which kind of member position 1 is — not which members exist, which is all a #
# row of the right width can express. The refusal is therefore the declared    #
# type's own: a decoded member row stands where a `str` is declared, and no    #
# `str` is what the writer says.                                               #
#                                                                              #
# The seam's own guarantee against a kind disagreement is a different one and  #
# is graded elsewhere: the construction compares the model it derives its      #
# layouts from against the classes it publishes, once per pair, and refuses    #
# with `entity-graph-layout-mismatch`                                          #
# (`test_publication_attachment.py`). It cannot reach this case, and correctly #
# so — the model that laid this row out is the Root View uses, not the one the        #
# construction resolved its classes under, so the two facts the check compares #
# agree here and the row is what disagrees with both.                          #
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

    fixture = PageFixture(_SCALAR_PROFILE, model=_PROFILE_AS_VALUE_OBJECT)
    node = fixture.node("MergeScalarProfile", {"id": 1, "profile": {"note": "x"}})
    with pytest.raises(GraphConstructionError) as refusal:
        fixture.materialize(node)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == AttributeIdentity(_MergeScalarProfile.identity, "profile")


# --------------------------------------------------------------------------- #
# Page pin and per-node edge.                                            #
# --------------------------------------------------------------------------- #
def test_a_temporal_node_carries_the_page_pin_and_its_own_edge() -> None:
    fixture = PageFixture(read_models.BALANCE_MODEL)
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


def test_temporal_starts_distinguish_page_logical_identity() -> None:
    fixture = PageFixture(read_models.BALANCE_MODEL)
    first_start = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
    second_start = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)
    first = fixture.node(
        "Balance",
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("5.00"),
            "in_z": first_start,
            "out_z": second_start,
        },
    )
    second = fixture.node(
        "Balance",
        {
            "bal_id": 1,
            "acct_num": "A-1",
            "val": Decimal("7.00"),
            "in_z": second_start,
            "out_z": dt.datetime(2024, 3, 1, tzinfo=dt.UTC),
        },
    )
    page = fixture.page(first, second)

    RootView(page, 0)
    RootView(page, 1)
    rows = page_rows(page)
    first_key, second_key = rows.keys[first], rows.keys[second]
    assert first_key is not None and second_key is not None
    assert [first_key.coordinates, second_key.coordinates] == [(first_start,), (second_start,)]
    assert len(page.judged_states) == 2


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
    fixture = PageFixture(_TEMPORAL_TPCS)
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
# The Page boundary: edges and roots are exact in-range projection indexes.   #
# --------------------------------------------------------------------------- #
_ORDER_IDENTITY = EntityIdentity(_NAMESPACE, "SnapOrder")
_ITEMS = RelationshipViewKey(RelationshipIdentity(_ORDER_IDENTITY, "items"))


class _Ordinal(IntEnum):
    FIRST = 0


def _one_projection() -> tuple[PageBuilder, int]:
    """One builder holding exactly one projection, so ``1`` is out of range."""
    fixture = PageFixture(_ORDERS)
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
    with pytest.raises(ValueError, match="outside this Page's 1 projections"):
        builder.write_view(order, _ITEMS, value)


def test_a_to_many_edge_is_refused_element_by_element() -> None:
    builder, order = _one_projection()
    with pytest.raises(ValueError, match="a to-many relationship view names projection 4"):
        builder.write_view(order, _ITEMS, (0, 4))


def test_a_view_this_projections_own_level_never_attaches_is_refused() -> None:
    # A view row has no position for a level that does not attach here, and the
    # refusal is what keeps that a fact about the plan rather than a silent
    # write into whichever slot happened to be nearby.
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrder.items")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    with pytest.raises(ValueError, match="no level below source 0 attaches 'order'"):
        fixture.attach(order, "parallax.compatibility.SnapOrderItem.order", None)


def test_a_loaded_view_naming_a_direction_the_concrete_lacks_is_refused() -> None:
    # The complement of the check above, and the one a positional row moves. A
    # view schema lays out a slot for a name the concrete does not declare — the
    # canonical view order ranks an unknown name last rather than refusing it —
    # so writing that slot is a disagreement the row can only meet when the name
    # is translated to a position. It stays a closed construction code there
    # rather than becoming a `KeyError` out of the index the translation reads.
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrder.zzz")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    fixture.attach(order, "parallax.compatibility.SnapOrder.zzz", None)
    with pytest.raises(GraphConstructionError) as refusal:
        fixture.materialize(order)
    assert refusal.value.code == "entity-graph-invalid-member"
    assert refusal.value.index == 0
    assert refusal.value.identity == RelationshipIdentity(_ORDER_IDENTITY, "zzz")


def test_a_loaded_view_naming_another_entitys_direction_of_the_same_name_is_refused() -> None:
    # `statuses` is declared by SnapOrder and, separately, by SnapOrderItem, so a
    # view carrying the item's direction names a position the order has under a
    # direction it does not navigate. The whole Relationship Identity is what
    # locates a position, so this is the same refusal an unknown name takes
    # rather than a silent write of the foreign arm at the declared one's index.
    foreign = RelationshipIdentity(EntityIdentity(_NAMESPACE, "SnapOrderItem"), "statuses")
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrderItem.statuses")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    fixture.attach(order, "parallax.compatibility.SnapOrderItem.statuses", ())
    with pytest.raises(GraphConstructionError) as refusal:
        fixture.materialize(order)
    assert refusal.value.code == "entity-graph-invalid-member"
    assert refusal.value.index == 0
    assert refusal.value.identity == foreign


def test_a_root_outside_the_page_is_refused_at_sealing() -> None:
    builder, _ = _one_projection()
    with pytest.raises(ValueError, match="a root names projection 3"):
        builder.finish((3,), Pin())


def test_a_sealed_builder_refuses_every_further_use() -> None:
    fixture = PageFixture(_ORDERS)
    order = fixture.node("SnapOrder", _ORDER_ROW)
    builder = fixture.builder
    builder.finish((order,), Pin())
    for use in (
        lambda: builder.write_view(order, _ITEMS, None),
        lambda: builder.concrete_of(order),
        lambda: builder.finish((order,), Pin()),
    ):
        with pytest.raises(ValueError, match="finished its arrays"):
            use()


def test_a_sealed_builder_holds_none_of_what_it_accumulated() -> None:
    # Sealing transfers the accumulation, so a caller who keeps the sealed
    # builder keeps nothing the sealed Page carries — the stored-data issue
    # records and their frozen evidence included, which is the only accumulator
    # a caller cannot reach through the refusals above. Read over the declared
    # slots rather than a list written here, so an accumulator added later is
    # held to this without the case being remembered.
    fixture = PageFixture(_STORY_ORDERS, "parallax.compatibility.Order.items")
    order = fixture.node("Order", _ORDER_ROW)
    item = fixture.node("OrderItem", {**_ITEM_ROW, "shipped_on": "not-a-date"})
    fixture.attach(order, "parallax.compatibility.Order.items", (item,))
    builder = fixture.builder
    kept = ("_schema", "_sealed")
    accumulators = tuple(name for name in PageBuilder.__slots__ if name not in kept)

    assert any(getattr(builder, name) for name in accumulators)
    fixture.page(order)
    assert [name for name in accumulators if getattr(builder, name)] == []


def test_a_root_view_refuses_an_unfinished_builder() -> None:
    builder, _ = _one_projection()
    with pytest.raises(TypeError, match="requires a finished Page"):
        RootView(builder)  # pyright: ignore[reportArgumentType]


# --------------------------------------------------------------------------- #
# The indexed Root View answers by reference, never by composition.                #
# --------------------------------------------------------------------------- #
def test_every_root_view_accessor_answers_the_identical_object_on_a_second_call() -> None:
    # The interface exists to remove per-node composition, so equality would
    # pass over exactly the defect it forbids: two equal answers built twice.
    # The root-wide properties are held to the same rule as the per-node
    # reads, over a Root View whose every one of them is nonempty — a resolved node
    # with duplicate projections, a loaded to-many, and a keyless root.
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrder.items")
    order = fixture.node("SnapOrder", _ORDER_ROW)
    first = fixture.node("SnapOrderItem", _ITEM_ROW)
    second = fixture.node("SnapOrderItem", {**_ITEM_ROW, "id": 12})
    duplicate = fixture.node("SnapOrder", _ORDER_ROW)
    keyless = fixture.node("SnapOrder", {**_ORDER_ROW, "id": None})
    fixture.attach(order, "parallax.compatibility.SnapOrder.items", (first, second))
    root_view = RootView(fixture.page(order, keyless, duplicate))

    assert root_view.layout(0) is root_view.layout(0)
    assert root_view.member_values(0) is root_view.member_values(0)
    assert root_view.issues(0) is root_view.issues(0)
    assert root_view.view_layout(0) is root_view.view_layout(0)
    assert root_view.view(0, 0) is root_view.view(0, 0)
    assert root_view.view(0, 0) == (1, 2)

    assert root_view.order is root_view.order
    assert root_view.roots is root_view.roots
    assert root_view.invalid_roots is root_view.invalid_roots
    assert root_view.roots == (0, None, 0)
    assert len(root_view.order) == 3
    assert [record.ordinal for record in root_view.invalid_roots] == [1]


def test_one_view_shape_is_shared_by_every_node_that_carries_it() -> None:
    # Two Orders reached one way carry one shared view layout, so the ordering
    # rule runs once per shape rather than once per node.
    fixture = PageFixture(_ORDERS, "parallax.compatibility.SnapOrder.items")
    first = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 1})
    second = fixture.node("SnapOrder", {**_ORDER_ROW, "id": 2})
    fixture.attach(first, "parallax.compatibility.SnapOrder.items", ())
    fixture.attach(second, "parallax.compatibility.SnapOrder.items", ())
    root_view = RootView(fixture.page(first, second))
    assert root_view.view_layout(0) is root_view.view_layout(1)


def test_a_member_the_read_did_not_carry_reads_absent_rather_than_null() -> None:
    fixture = PageFixture(_ORDERS)
    order = fixture.node("SnapOrder", {key: _ORDER_ROW[key] for key in ("id", "name")})
    root_view = RootView(fixture.page(order))
    layout = root_view.layout(0)
    values = root_view.member_values(0)
    assert values[layout.index_of[AttributeIdentity(_ORDER_IDENTITY, "name")]] == "Ada"
    assert values[layout.index_of[AttributeIdentity(_ORDER_IDENTITY, "sku")]] is ABSENT
    # A failed assertion over a row has to name the absence it found, so the
    # sentinel spells itself rather than an address.
    assert repr(ABSENT) == "ABSENT"


def test_two_unreadable_projections_of_one_row_never_share_with_each_other() -> None:
    # An invalid key short-circuits identity entirely, so a second read of the
    # identical unreadable row is a second logical node rather than the same one
    # diagnosed twice — which is what keeps each physical finding attributable.
    fixture = PageFixture(_ORDERS)
    unreadable = {**_ORDER_ROW, "id": None}
    first = fixture.node("SnapOrder", unreadable)
    second = fixture.node("SnapOrder", unreadable)
    readable = fixture.node("SnapOrder", _ORDER_ROW)
    again = fixture.node("SnapOrder", _ORDER_ROW)
    root_view = RootView(fixture.page(first, second, readable, again))
    # Both unreadable roots are invalid-root holes, and the two readable ones
    # collapse onto one allocation — so the Root View allocated one node, not three.
    assert root_view.roots == (None, None, 0, 0)
    assert len(root_view.order) == 1
    assert [record.ordinal for record in root_view.invalid_roots] == [0, 1]


def test_one_rejected_subtree_reached_twice_retains_one_frozen_copy() -> None:
    # A scalar rejected value costs nothing to hold twice, and Python may hand
    # two rows the identical string anyway. A rejected document subtree is the
    # shape the retention rule is about: two rows decode two independent
    # structures and each freezes its own, and only the copy the resolved node
    # retains stays alive once the second row's conversion returns.
    stored: dict[str, object] = {
        "id": 1,
        "name": "Ada",
        "address": {"street": "1 Park Ave", "phones": {"type": "home"}},
    }
    fixture = PageFixture(vo_models.CUSTOMER_MODEL)
    first = fixture.node("Customer", dict(stored))
    second = fixture.node("Customer", dict(stored))
    page = fixture.page(first, second)
    root = RootView(page)
    (frozen,) = root.issues(0)
    assert frozen.stored_value == {"type": "home"}
    assert root.issues(0) == (frozen,)


def test_no_published_value_is_the_absent_sentinel() -> None:
    # ABSENT is this runtime's own spelling of a position a read did not carry,
    # and it is never a value: a consumer skips the position, so what publishes
    # is a member the value does not have rather than a member holding a marker.
    fixture = PageFixture(_ORDERS)
    order = fixture.node("SnapOrder", {key: _ORDER_ROW[key] for key in ("id", "name")})
    (root,) = fixture.materialize(order)
    assert isinstance(root, sm.SnapOrder)
    assert "sku" not in root.model_fields_set
    assert all(value is not ABSENT for value in vars(root).values())


def _customer_row(phone_type: str) -> dict[str, object]:
    """One stored Customer rejected twice over: an array where the ``geo``
    object belongs — identical in every row — and an object where ``phones``
    holds an array, spelled per row by ``phone_type``."""
    return {
        "id": 1,
        "name": "Ada",
        "address": {
            "street": "1 Park Ave",
            "geo": [{"country": "GB", "elevation": 3.0}],
            "phones": {"type": phone_type},
        },
    }


def _sole_node(root_view: Any, name: str) -> int:
    (index,) = [index for index, entity in enumerate(root_view.order) if entity.name == name]
    return index
