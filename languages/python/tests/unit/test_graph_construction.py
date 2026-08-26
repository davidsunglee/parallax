"""The advanced Entity Graph Construction collaboration
(``parallax.core.entity._graph_construction``): the two positional rows that
cross its door, the three-phase barrier, handle and scope rules, the
deterministic allocation index every rejection reads back, and the all-or-none
lifecycle-state attachment that makes a failed construction return no root and
attach no state to any node.

Driven directly rather than through Snapshot, because the contract is the roots a
caller gives and what is reachable from them — never "the query result".

Every row here is written as a literal tuple against the exact Entity's member
layout, rather than assembled from that layout by name. A row assembled from the
layout would agree with the writer however either end drifted; a literal one is
what makes the alignment between the two a thing this suite can be wrong about.
`test_the_writers_relationship_order_is_the_layouts_own` closes the same gap for
the two derivations of the canonical relationship order.
"""

from __future__ import annotations

import datetime as dt
import warnings
from decimal import Decimal
from typing import Any, cast

import pytest

from _support import snapshot_models as sm
from parallax.core import Attr, Bitemporal, attr
from parallax.core.base import INFINITY
from parallax.core.entity import (
    GRAPH_CONSTRUCTION_CODES,
    UNLOADED,
    EntityGraphWriter,
    GraphConstructionError,
    NodeHandle,
    ResolutionView,
    graph_construction_of,
    lifecycle_state_of,
    relationship_value_of,
)
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._layout import LayoutCatalog
from parallax.core.entity._model import DomainModel, model_of
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    RelationshipIdentity,
    UnresolvedEntityDeclaration,
)

_ORDERS = sm.SNAP_ORDERS_MODEL
_ORDER = sm.SnapOrder.identity
_ITEM = sm.SnapOrderItem.identity


def _attr(entity: EntityIdentity, name: str) -> AttributeIdentity:
    return AttributeIdentity(entity, name)


def _rel(entity: EntityIdentity, name: str) -> RelationshipIdentity:
    return RelationshipIdentity(entity, name)


# `SnapOrder`: id, name, sku, qty, price, active, orderedOn — then items, statuses.
_ORDER_MEMBERS: tuple[object, ...] = (1, "Ada", None, 1, Decimal("1.00"), True, dt.date(2024, 1, 1))
_ORDER_UNLOADED: tuple[object, ...] = (UNLOADED, UNLOADED)

# `SnapOrderItem`: id, orderId, sku, quantity, shippedOn — then order, statuses.
_ITEM_MEMBERS: tuple[object, ...] = (11, 1, "x", 1, None)
_ITEM_UNLOADED: tuple[object, ...] = (UNLOADED, UNLOADED)


def _construct(build: Any, *, state_factory: Any = None) -> tuple[object, ...]:
    return graph_construction_of(_ORDERS).construct(build, state_factory=state_factory)


class _ClasslessSource:
    """A minimal Unresolved Metamodel composing no Entity Class — the descriptor
    frontend's own formation input, and the one route to a model with no class
    index."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (sm.SnapOrderStatus,)


class _CallerDefinedTuple(tuple[Any, ...]):
    """A caller-defined collection subtype: a ``tuple`` for ``isinstance``, and
    still not the exact built-in the seams take."""


def _one_order(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
    handle = writer.allocate(_ORDER)
    writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
    return (handle,)


# --------------------------------------------------------------------------- #
# Allocation, population, and the cycle the barrier exists for.                #
# --------------------------------------------------------------------------- #


def test_construct_publishes_frozen_instances_of_the_composed_classes() -> None:
    (root,) = _construct(_one_order)
    assert isinstance(root, sm.SnapOrder)
    assert (root.id, root.name, root.qty) == (1, "Ada", 1)
    assert root.sku is None


def test_an_allocated_shell_closes_a_cycle_before_either_node_is_populated() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        item = writer.allocate(_ITEM)
        writer.populate(order, _ORDER_MEMBERS, ((item,), UNLOADED))
        writer.populate(item, _ITEM_MEMBERS, (order, UNLOADED))
        return (order,)

    (root,) = _construct(build)
    root = cast("sm.SnapOrder", root)
    assert root.items[0].order is root


def test_an_unnamed_relationship_view_installs_the_closed_world_sentinel() -> None:
    (root,) = _construct(_one_order)
    assert relationship_value_of(root, _rel(_ORDER, "items")) is UNLOADED
    assert relationship_value_of(root, _rel(_ORDER, "statuses")) is UNLOADED


def test_loaded_null_and_loaded_empty_stay_distinct_from_unloaded() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        item = writer.allocate(_ITEM)
        writer.populate(order, _ORDER_MEMBERS, ((), UNLOADED))
        writer.populate(item, _ITEM_MEMBERS, (None, UNLOADED))
        return (order, item)

    order, item = _construct(build)
    assert cast("sm.SnapOrder", order).items == ()
    assert cast("sm.SnapOrderItem", item).order is None
    assert relationship_value_of(order, _rel(_ORDER, "statuses")) is UNLOADED


def test_roots_are_published_in_the_order_the_build_callback_answers() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        first = writer.allocate(_ORDER)
        second = writer.allocate(_ITEM)
        writer.populate(first, _ORDER_MEMBERS, _ORDER_UNLOADED)
        writer.populate(second, _ITEM_MEMBERS, _ITEM_UNLOADED)
        return (second, first)

    published = _construct(build)
    assert [type(node) for node in published] == [sm.SnapOrderItem, sm.SnapOrder]


def test_an_absent_member_position_leaves_its_declared_default_in_place() -> None:
    # A positional row cannot omit, so absence is a value at the position. What it
    # buys is what omitting an entry bought: the member is never written, so it
    # reads back as its declared default and its presence bit stays clear.
    #
    # A published Entity now records presence per member, exactly as a published
    # Value Object does: the bitmap its row carries is what `model_fields_set`
    # answers from, so an absent position and a carried one are distinguishable
    # where publication once left them identical.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, (1, "Ada", ABSENT, ABSENT, ABSENT, ABSENT, ABSENT), _ORDER_UNLOADED)
        return (handle,)

    (root,) = _construct(build)
    order = cast("sm.SnapOrder", root)
    assert (order.id, order.name) == (1, "Ada")
    assert order.sku is None
    assert order.model_fields_set == {"id", "name"}


# --------------------------------------------------------------------------- #
# The phase barrier and the rejections that read the allocation index back.    #
# --------------------------------------------------------------------------- #


def test_allocation_closes_permanently_at_the_first_populate() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, _ORDER_UNLOADED)
        writer.allocate(_ITEM)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-allocation-closed"
    assert refusal.value.index == 1


def test_populating_one_node_twice_is_refused_with_its_allocation_index() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, _ORDER_UNLOADED)
        writer.populate(order, _ORDER_MEMBERS, _ORDER_UNLOADED)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-node-already-populated"
    assert refusal.value.index == 0


def test_the_lowest_unpopulated_index_is_the_one_reported() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.allocate(_ITEM)
        writer.allocate(_ITEM)
        writer.populate(order, _ORDER_MEMBERS, _ORDER_UNLOADED)
        return (order,)

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-node-unpopulated"
    assert refusal.value.index == 1


def test_allocating_an_entity_the_model_composed_no_class_for_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.allocate(EntityIdentity("parallax.compatibility", "Nowhere"))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-entity"


def test_a_retained_writer_refuses_before_inspecting_its_arguments() -> None:
    escaped: list[EntityGraphWriter] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        escaped.append(writer)
        return ()

    _construct(build)
    with pytest.raises(GraphConstructionError) as refusal:
        escaped[0].populate(cast("Any", "not a handle"), (), ())
    assert refusal.value.code == "entity-graph-scope-closed"


def test_a_handle_from_another_construction_is_refused_as_foreign() -> None:
    escaped: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        escaped.append(handle)
        return (handle,)

    _construct(build)

    def reuse(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.populate(escaped[0], _ORDER_MEMBERS, _ORDER_UNLOADED)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(reuse)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_foreign_handle_answered_as_a_root_is_refused_as_foreign() -> None:
    escaped: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        escaped.append(handle)
        return (handle,)

    _construct(build)

    def answer_foreign(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        return (escaped[0],)

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(answer_foreign)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_foreign_handle_at_a_relationship_position_is_refused_as_foreign() -> None:
    escaped: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ITEM)
        writer.populate(handle, _ITEM_MEMBERS, _ITEM_UNLOADED)
        escaped.append(handle)
        return (handle,)

    _construct(build)

    def name_foreign(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, ((escaped[0],), UNLOADED))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(name_foreign)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_build_callback_answering_something_other_than_handles_is_refused() -> None:
    def answers_a_list(writer: EntityGraphWriter) -> Any:
        del writer
        return []

    def answers_a_tuple_subclass(writer: EntityGraphWriter) -> Any:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        return _CallerDefinedTuple((handle,))

    def answers_a_string(writer: EntityGraphWriter) -> Any:
        del writer
        return ("root",)

    with pytest.raises(GraphConstructionError) as not_a_tuple:
        _construct(answers_a_list)
    assert not_a_tuple.value.code == "entity-graph-invalid-root"

    with pytest.raises(GraphConstructionError) as not_exactly_a_tuple:
        _construct(answers_a_tuple_subclass)
    assert not_exactly_a_tuple.value.code == "entity-graph-invalid-root"

    with pytest.raises(GraphConstructionError) as not_a_handle:
        _construct(answers_a_string)
    assert not_a_handle.value.code == "entity-graph-invalid-root"


def test_a_build_callback_exception_propagates_unchanged() -> None:
    class _Boom(RuntimeError):
        pass

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.allocate(_ORDER)
        raise _Boom("the caller's own failure")

    with pytest.raises(_Boom, match="the caller's own failure"):
        _construct(build)


# --------------------------------------------------------------------------- #
# Row shape, row width, and value validation.                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "members",
    [
        pytest.param((*_ORDER_MEMBERS, 1), id="one-position-too-many"),
        pytest.param(_ORDER_MEMBERS[:-1], id="one-position-too-few"),
        pytest.param((), id="no-positions-at-all"),
    ],
)
def test_a_member_row_of_the_wrong_width_is_refused(members: Any) -> None:
    # Width is the whole membership check a positional row needs. A position
    # names one declared member and nothing else, so an undeclared member has no
    # position to occupy and a duplicate has one position to occupy — the two
    # rejections the identity-keyed algebra made separately are unrepresentable
    # rather than checked. What is left to refuse is a row of any other width.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, members, _ORDER_UNLOADED)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"
    assert refusal.value.index == 0


@pytest.mark.parametrize(
    "relationships",
    [
        pytest.param((UNLOADED,), id="one-position-too-few"),
        pytest.param((UNLOADED, UNLOADED, UNLOADED), id="one-position-too-many"),
    ],
)
def test_a_broad_relationship_row_of_the_wrong_width_is_refused(relationships: Any) -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, relationships)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


def test_a_null_on_a_non_nullable_attribute_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, (1, None, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT), _ORDER_UNLOADED)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == _attr(_ORDER, "name")


def test_a_value_outside_the_declared_neutral_type_is_refused() -> None:
    # Declared-type enforcement on a materialized read is the writer's own
    # Neutral Value check: construction bypasses Pydantic validation entirely, so
    # a `str` where a `date` is declared has nothing else standing between it and
    # the frozen instance.
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(
            order,
            (1, "Ada", ABSENT, ABSENT, ABSENT, ABSENT, "2024-01-01"),
            _ORDER_UNLOADED,
        )
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == _attr(_ORDER, "orderedOn")


def test_a_to_many_direction_refuses_a_to_one_arm() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, (None, UNLOADED))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == _rel(_ORDER, "items")


def test_a_to_one_direction_refuses_a_loaded_many_arm() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        item = writer.allocate(_ITEM)
        writer.populate(item, _ITEM_MEMBERS, ((), UNLOADED))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == _rel(_ITEM, "order")


def test_a_node_handle_publishes_nothing_a_build_callback_could_read() -> None:
    # The handle is the whole of what a callback holds between allocation and
    # publication, so a public attribute on it would hand that callback the
    # partially built instances a failed construction must leave unreachable, and
    # an allocation index the writer alone owns.
    captured: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        captured.append(handle)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        return (handle,)

    _construct(build)
    handle = captured[0]
    assert [name for name in dir(handle) if not name.startswith("__")] == []
    with pytest.raises(AttributeError):
        cast("Any", handle).index = 0


@pytest.mark.parametrize(
    "collection",
    [
        pytest.param(list, id="a-mutable-collection"),
        pytest.param(_CallerDefinedTuple, id="a-caller-defined-collection-subtype"),
    ],
)
def test_a_loaded_many_arm_carries_only_an_exact_tuple_of_handles(collection: Any) -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        item = writer.allocate(_ITEM)
        writer.populate(item, _ITEM_MEMBERS, _ITEM_UNLOADED)
        writer.populate(order, _ORDER_MEMBERS, (collection((item,)), UNLOADED))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_value_that_is_no_relationship_arm_at_all_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        item = writer.allocate(_ITEM)
        writer.populate(item, _ITEM_MEMBERS, ("not an arm", UNLOADED))
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


def test_the_writers_relationship_order_is_the_layouts_own() -> None:
    # The broad-relationship row is built by a caller against the member layout's
    # canonical order and read by the writer against its own derivation of that
    # same rule. Two derivations that disagreed would install every arm at the
    # wrong direction silently, which is the one hazard a positional row adds and
    # the sparse algebra's identities used to rule out.
    catalog = LayoutCatalog(model_of(_ORDERS))
    construction = graph_construction_of(_ORDERS)
    for entity in (_ORDER, _ITEM, sm.SnapOrderStatus.identity):
        facts = construction.facts_for(entity)
        assert tuple(direction.identity for direction in facts.relationships) == (
            catalog.entity(entity).relationships
        )


# --------------------------------------------------------------------------- #
# Recursive Value Object construction.                                         #
# --------------------------------------------------------------------------- #

_STATUS = sm.SnapOrderStatus.identity

# `SnapOrderStatus`: id, orderId, orderItemId, code — then primaryTag, tags.
# A `Tag` member row is label, detail, details.
_STATUS_MEMBERS: tuple[object, ...] = (21, 1, None, "SHIPPED", ABSENT, ABSENT)


def _tag(label: object, *, detail: object = ABSENT, details: object = ABSENT) -> tuple[object, ...]:
    return (label, detail, details)


def _status(*, primary: object = ABSENT, tags: object = ABSENT) -> Any:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        status = writer.allocate(_STATUS)
        writer.populate(status, (*_STATUS_MEMBERS[:4], primary, tags), ())
        return (status,)

    return build


def test_a_value_object_occurrence_builds_a_frozen_instance() -> None:
    (root,) = _construct(_status(primary=_tag("urgent")))
    tag = cast("Any", root).primary_tag
    assert isinstance(tag, sm.Tag)
    assert tag.label == "urgent"
    # An absent nested occurrence reads as absent at every depth: `None` for a
    # One, the empty tuple for a Many.
    assert tag.detail is None
    assert tag.details == ()


def test_a_nested_occurrence_builds_recursively_in_declaration_order() -> None:
    (root,) = _construct(_status(primary=_tag("x", detail=("handled",))))
    assert cast("Any", root).primary_tag.detail.note == "handled"


def test_a_many_occurrence_preserves_its_record_order() -> None:
    (root,) = _construct(_status(tags=(_tag("first"), _tag("second"))))
    assert [tag.label for tag in cast("Any", root).tags] == ["first", "second"]


@pytest.mark.parametrize(
    "collection",
    [
        pytest.param(list, id="a-mutable-collection"),
        pytest.param(_CallerDefinedTuple, id="a-caller-defined-collection-subtype"),
    ],
)
def test_a_many_occurrence_refuses_anything_but_an_exact_tuple(collection: Any) -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(tags=collection((_tag("x"),))))
    assert refusal.value.code == "entity-graph-invalid-value"


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(("x", ABSENT, ABSENT, ABSENT), id="one-position-too-many"),
        pytest.param(("x", ABSENT), id="one-position-too-few"),
    ],
)
def test_a_value_object_member_row_of_the_wrong_width_is_refused(row: Any) -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(primary=row))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_value_object_leaf_outside_its_declared_type_is_refused() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(primary=_tag(7)))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_raw_document_mapping_never_crosses_the_construction_seam() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(primary={"label": "x"}))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_many_occurrence_is_never_null() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(tags=None))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_null_one_occurrence_is_the_documents_own_absent_state() -> None:
    # A One occurrence absent from the document, stored as JSON null, or stored
    # in the wrong kind all reach construction as `None`, because the read seam
    # already collapsed them into one not-present state. Re-deriving a
    # nullability verdict here would contradict that collapse.
    (root,) = _construct(_status(primary=None))
    assert cast("Any", root).primary_tag is None


# --------------------------------------------------------------------------- #
# Native infinity, admitted only where a temporal interval is left open.        #
# --------------------------------------------------------------------------- #


class _Milestone(Bitemporal, table="graph_milestone", name="Milestone", namespace="parallax.test"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


_MILESTONES = DomainModel(_Milestone)
_MILESTONE = _Milestone.identity

# `_Milestone`: id, amount, validStart, validEnd, txStart, txEnd — no relationships.
_MILESTONE_BOUNDS: tuple[str, ...] = ("validStart", "validEnd", "txStart", "txEnd")


def _bound(name: str) -> tuple[object, ...]:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        node = writer.allocate(_MILESTONE)
        writer.populate(
            node,
            (
                1,
                Decimal("1.00"),
                *(INFINITY if bound == name else ABSENT for bound in _MILESTONE_BOUNDS),
            ),
            (),
        )
        return (node,)

    return graph_construction_of(_MILESTONES).construct(build)


@pytest.mark.parametrize("name", ["txEnd", "validEnd"])
def test_a_temporal_end_attribute_carries_the_open_upper_bound(name: str) -> None:
    (root,) = _bound(name)
    assert getattr(root, "tx_end" if name == "txEnd" else "valid_end") is INFINITY


@pytest.mark.parametrize("name", ["txStart", "validStart"])
def test_a_temporal_start_attribute_admits_no_infinity(name: str) -> None:
    # Native infinity is the OPEN UPPER BOUND of a temporal interval (m-core);
    # a milestone's start is a finite instant like any other timestamp, however
    # framework-owned both endpoints are.
    with pytest.raises(GraphConstructionError) as refusal:
        _bound(name)
    assert refusal.value.code == "entity-graph-invalid-value"
    assert refusal.value.identity == _attr(_MILESTONE, name)


# --------------------------------------------------------------------------- #
# Publishing a subtype, where a member's declaring class is not the published  #
# one: what a member the read did not carry reads back as, and dumps as.       #
# --------------------------------------------------------------------------- #

_CAT = sm.Cat.identity

# `Cat`: id, name, ownerId (Animal's), licenseId (Pet's), indoor (Cat's own).
_CAT_UNCARRIED: tuple[object, ...] = (1, "Tom", ABSENT, ABSENT, ABSENT)


def _cat(members: tuple[object, ...]) -> Any:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        node = writer.allocate(_CAT)
        writer.populate(node, members, ())
        return (node,)

    (root,) = graph_construction_of(sm.ANIMAL_MODEL).construct(build)
    return cast("Any", root)


def test_a_published_subtype_reads_an_uncarried_inherited_member_as_its_default() -> None:
    # `ownerId` is the family root's and `licenseId` the abstract middle's, so
    # this reads an absent member across both inheritance levels; the published
    # class's own `indoor` is the control.
    cat = _cat(_CAT_UNCARRIED)
    assert cat.owner_id is None
    assert cat.license_id is None
    assert cat.indoor is None


def test_a_published_subtype_serializes_an_uncarried_inherited_member() -> None:
    cat = _cat(_CAT_UNCARRIED)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        dumped = cat.model_dump()
    assert dumped == {
        "id": 1,
        "name": "Tom",
        "owner_id": None,
        "license_id": None,
        "indoor": None,
    }


def test_a_published_subtype_reads_a_carried_inherited_member_as_the_carried_value() -> None:
    cat = _cat((1, "Tom", 5, "L-1", True))
    assert (cat.owner_id, cat.license_id, cat.indoor) == (5, "L-1", True)


# --------------------------------------------------------------------------- #
# Lifecycle state: ordering, resolution scope, and atomic publication.         #
# --------------------------------------------------------------------------- #


def _two_nodes(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
    order = writer.allocate(_ORDER)
    item = writer.allocate(_ITEM)
    writer.populate(order, _ORDER_MEMBERS, ((item,), UNLOADED))
    writer.populate(item, _ITEM_MEMBERS, (order, UNLOADED))
    return (order,)


def test_state_factories_run_once_per_node_in_allocation_order() -> None:
    seen: list[type] = []

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        seen.append(type(view.resolve(handle)))
        return len(seen)

    (root,) = _construct(_two_nodes, state_factory=factory)
    assert seen == [sm.SnapOrder, sm.SnapOrderItem]
    assert lifecycle_state_of(root) == 1
    assert lifecycle_state_of(cast("sm.SnapOrder", root).items[0]) == 2


def test_a_factory_sees_every_instance_fully_wired_including_cycles() -> None:
    resolved: list[object] = []

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        node = view.resolve(handle)
        resolved.append(node)
        if isinstance(node, sm.SnapOrder):
            # The cycle is already closed while the FIRST factory runs, and no
            # state has attached to either end of it yet.
            assert node.items[0].order is node
            assert lifecycle_state_of(node.items[0]) is None
        return "state"

    _construct(_two_nodes, state_factory=factory)
    assert len(resolved) == 2


def test_a_resolution_view_closes_when_its_own_factory_invocation_returns() -> None:
    escaped: list[ResolutionView] = []

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        escaped.append(view)
        return view.resolve(handle)

    _construct(_one_order, state_factory=factory)
    with pytest.raises(GraphConstructionError) as refusal:
        escaped[0].resolve(cast("Any", "not a handle"))
    assert refusal.value.code == "entity-graph-scope-closed"


def test_a_resolution_view_refuses_a_handle_of_another_construction() -> None:
    escaped: list[NodeHandle] = []

    def collect(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_MEMBERS, _ORDER_UNLOADED)
        escaped.append(handle)
        return (handle,)

    _construct(collect)

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        del handle
        return view.resolve(escaped[0])

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_one_order, state_factory=factory)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_factory_exception_propagates_unchanged_and_stops_later_factories() -> None:
    class _Boom(RuntimeError):
        pass

    invoked: list[int] = []

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        del view, handle
        invoked.append(len(invoked))
        raise _Boom("the lifecycle's own failure")

    with pytest.raises(_Boom, match="the lifecycle's own failure"):
        _construct(_two_nodes, state_factory=factory)
    assert invoked == [0]


def test_a_failed_factory_publishes_no_state_on_any_node() -> None:
    captured: list[object] = []

    def factory(view: ResolutionView, handle: NodeHandle) -> object:
        node = view.resolve(handle)
        captured.append(node)
        if len(captured) == 2:
            raise RuntimeError("the second factory fails")
        return "state"

    with pytest.raises(RuntimeError, match="the second factory fails"):
        _construct(_two_nodes, state_factory=factory)
    # The first factory succeeded, but its result was only buffered: nothing
    # attaches unless every factory does.
    assert [lifecycle_state_of(node) for node in captured] == [None, None]


def test_construction_without_a_state_factory_attaches_no_state() -> None:
    (root,) = _construct(_one_order)
    assert lifecycle_state_of(root) is None


def test_reading_a_relationship_the_class_family_does_not_declare_is_refused() -> None:
    (root,) = _construct(_one_order)
    with pytest.raises(GraphConstructionError) as refusal:
        relationship_value_of(root, _rel(_ORDER, "nosuch"))
    assert refusal.value.code == "entity-graph-invalid-member"


def test_one_construction_is_reused_for_one_domain_model() -> None:
    assert graph_construction_of(_ORDERS) is graph_construction_of(_ORDERS)
    assert graph_construction_of(_ORDERS) is not graph_construction_of(sm.ANIMAL_MODEL)


# --------------------------------------------------------------------------- #
# The closed code set, and the row rules the collaboration states in it.       #
# --------------------------------------------------------------------------- #


# The ten codes Python spec §3 declares under "Entity Graph Construction
# surface". Restated here rather than imported so a code added, renamed, or
# dropped on either side fails instead of agreeing with itself.
_SPEC_CODES = frozenset(
    {
        "entity-graph-invalid-entity",
        "entity-graph-invalid-member",
        "entity-graph-invalid-value",
        "entity-graph-allocation-closed",
        "entity-graph-scope-closed",
        "entity-graph-node-already-populated",
        "entity-graph-node-unpopulated",
        "entity-graph-invalid-root",
        "entity-graph-foreign-handle",
        "entity-graph-layout-mismatch",
    }
)


def test_the_code_set_is_closed_against_an_unlisted_code() -> None:
    assert GRAPH_CONSTRUCTION_CODES == _SPEC_CODES
    assert len(GRAPH_CONSTRUCTION_CODES) == 10
    with pytest.raises(ValueError, match="not a graph construction code"):
        GraphConstructionError(code="entity-graph-nosuch", message="invented")


def test_a_model_that_composed_no_entity_class_can_construct_no_graph() -> None:
    descriptor_backed = DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.allocate(_ORDER)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        graph_construction_of(descriptor_backed).construct(build)
    assert refusal.value.code == "entity-graph-invalid-entity"


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(list(_ORDER_MEMBERS), id="an-abstract-sequence"),
        pytest.param(_CallerDefinedTuple(_ORDER_MEMBERS), id="a-caller-defined-collection-subtype"),
        pytest.param("idnamesku", id="a-value-that-is-no-row-at-all"),
    ],
)
def test_only_an_exact_tuple_crosses_the_seam(row: Any) -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, row, _ORDER_UNLOADED)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


@pytest.mark.parametrize(
    "row",
    [
        pytest.param([UNLOADED, UNLOADED], id="an-abstract-sequence"),
        pytest.param(
            _CallerDefinedTuple((UNLOADED, UNLOADED)), id="a-caller-defined-collection-subtype"
        ),
    ],
)
def test_only_an_exact_tuple_of_relationship_positions_crosses_the_seam(row: Any) -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_MEMBERS, row)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


def test_an_absent_value_object_leaf_reads_as_absent_rather_than_failing() -> None:
    # `Tag.label` is required, yet a document that omits it decoded to `ABSENT`
    # before construction saw it — the read seam's own absence collapse. The
    # frozen Value Object carries the member as absent, and construction neither
    # invents a value nor re-judges the collapse.
    (root,) = _construct(_status(primary=_tag(ABSENT)))
    tag = cast("Any", root).primary_tag
    assert tag.label is None
    assert "label" not in tag.model_fields_set


def test_an_absent_leaf_inside_a_many_element_reads_as_absent_too() -> None:
    # Absence is per element, not per occurrence: an element of a Many carries the
    # same distinction its One sibling does, so a document that omits a leaf in one
    # element and holds it in another builds two rows that differ in exactly
    # that. Without this, re-serializing the collection would spell an omission the
    # element never held as an explicit null.
    (root,) = _construct(_status(tags=(_tag(ABSENT), _tag("named"))))
    absent, named = cast("Any", root).tags
    assert absent.label is None
    assert "label" not in absent.model_fields_set
    assert named.label == "named"
    assert "label" in named.model_fields_set
