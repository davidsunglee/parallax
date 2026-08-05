"""The advanced Entity Graph Construction collaboration
(``parallax.core.entity._graph_construction``): the three-phase barrier, handle
and scope rules, the deterministic allocation index every rejection reads back,
and the all-or-none publication that makes a failed construction leave nothing
reachable.

Driven directly rather than through Snapshot, because the contract is the roots a
caller gives and what is reachable from them — never "the query result".
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any, cast

import pytest

from _support import snapshot_models as sm
from parallax.core.entity import (
    GRAPH_CONSTRUCTION_CODES,
    LOADED_NULL,
    UNLOADED,
    UNLOADED_VIEW,
    EntityAttributeInput,
    EntityGraphWriter,
    EntityRelationshipInput,
    GraphConstructionError,
    LoadedMany,
    LoadedOne,
    NodeHandle,
    ResolutionView,
    ValueObjectAttributeInput,
    ValueObjectOccurrenceInput,
    ValueObjectRecord,
    entity_runtime_of,
    lifecycle_state_of,
    relationship_value_of,
)
from parallax.core.entity._model import DomainModel
from parallax.core.metamodel import (
    AttributeIdentity,
    EntityIdentity,
    RelationshipIdentity,
    UnresolvedEntityDeclaration,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
)

_ORDERS = sm.SNAP_ORDERS_MODEL
_ORDER = sm.SnapOrder.identity
_ITEM = sm.SnapOrderItem.identity


def _attr(entity: EntityIdentity, name: str) -> AttributeIdentity:
    return AttributeIdentity(entity, name)


def _rel(entity: EntityIdentity, name: str) -> RelationshipIdentity:
    return RelationshipIdentity(entity, name)


_ORDER_SCALARS: tuple[EntityAttributeInput, ...] = (
    EntityAttributeInput(_attr(_ORDER, "id"), 1),
    EntityAttributeInput(_attr(_ORDER, "name"), "Ada"),
    EntityAttributeInput(_attr(_ORDER, "sku"), None),
    EntityAttributeInput(_attr(_ORDER, "qty"), 1),
    EntityAttributeInput(_attr(_ORDER, "price"), Decimal("1.00")),
    EntityAttributeInput(_attr(_ORDER, "active"), True),
    EntityAttributeInput(_attr(_ORDER, "orderedOn"), dt.date(2024, 1, 1)),
)

_ITEM_SCALARS: tuple[EntityAttributeInput, ...] = (
    EntityAttributeInput(_attr(_ITEM, "id"), 11),
    EntityAttributeInput(_attr(_ITEM, "orderId"), 1),
    EntityAttributeInput(_attr(_ITEM, "sku"), "x"),
    EntityAttributeInput(_attr(_ITEM, "quantity"), 1),
    EntityAttributeInput(_attr(_ITEM, "shippedOn"), None),
)


def _construct(build: Any, *, state_factory: Any = None) -> tuple[object, ...]:
    return entity_runtime_of(_ORDERS).construct(build, state_factory=state_factory)


class _ClasslessSource:
    """A minimal Unresolved Metamodel composing no Entity Class — the descriptor
    frontend's own formation input, and the one route to a model with no class
    index."""

    @property
    def entities(self) -> tuple[UnresolvedEntityDeclaration, ...]:
        return (sm.SnapOrderStatus,)


def _one_order(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
    handle = writer.allocate(_ORDER)
    writer.populate(handle, _ORDER_SCALARS, (), ())
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
        writer.populate(
            order,
            _ORDER_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ORDER, "items"), LoadedMany((item,))),),
        )
        writer.populate(
            item,
            _ITEM_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ITEM, "order"), LoadedOne(order)),),
        )
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
        writer.populate(
            order,
            _ORDER_SCALARS,
            (),
            (
                EntityRelationshipInput(_rel(_ORDER, "items"), LoadedMany(())),
                EntityRelationshipInput(_rel(_ORDER, "statuses"), UNLOADED_VIEW),
            ),
        )
        writer.populate(
            item,
            _ITEM_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ITEM, "order"), LOADED_NULL),),
        )
        return (order, item)

    order, item = _construct(build)
    assert cast("sm.SnapOrder", order).items == ()
    assert cast("sm.SnapOrderItem", item).order is None
    assert relationship_value_of(order, _rel(_ORDER, "statuses")) is UNLOADED


def test_roots_are_published_in_the_order_the_build_callback_answers() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        first = writer.allocate(_ORDER)
        second = writer.allocate(_ITEM)
        writer.populate(first, _ORDER_SCALARS, (), ())
        writer.populate(second, _ITEM_SCALARS, (), ())
        return (second, first)

    published = _construct(build)
    assert [type(node) for node in published] == [sm.SnapOrderItem, sm.SnapOrder]


# --------------------------------------------------------------------------- #
# The phase barrier and the rejections that read the allocation index back.    #
# --------------------------------------------------------------------------- #


def test_allocation_closes_permanently_at_the_first_populate() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_SCALARS, (), ())
        writer.allocate(_ITEM)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-allocation-closed"
    assert refusal.value.index == 1


def test_populating_one_node_twice_is_refused_with_its_allocation_index() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, _ORDER_SCALARS, (), ())
        writer.populate(order, _ORDER_SCALARS, (), ())
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
        writer.populate(order, _ORDER_SCALARS, (), ())
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
        escaped[0].populate(cast("Any", "not a handle"), (), (), ())
    assert refusal.value.code == "entity-graph-scope-closed"


def test_a_handle_from_another_construction_is_refused_as_foreign() -> None:
    escaped: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_SCALARS, (), ())
        escaped.append(handle)
        return (handle,)

    _construct(build)

    def reuse(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.populate(escaped[0], _ORDER_SCALARS, (), ())
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(reuse)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_foreign_handle_answered_as_a_root_is_refused_as_foreign() -> None:
    escaped: list[NodeHandle] = []

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_SCALARS, (), ())
        escaped.append(handle)
        return (handle,)

    _construct(build)

    def answer_foreign(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        handle = writer.allocate(_ORDER)
        writer.populate(handle, _ORDER_SCALARS, (), ())
        return (escaped[0],)

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(answer_foreign)
    assert refusal.value.code == "entity-graph-foreign-handle"


def test_a_build_callback_answering_something_other_than_handles_is_refused() -> None:
    def answers_a_list(writer: EntityGraphWriter) -> Any:
        del writer
        return []

    def answers_a_string(writer: EntityGraphWriter) -> Any:
        del writer
        return ("root",)

    with pytest.raises(GraphConstructionError) as not_a_tuple:
        _construct(answers_a_list)
    assert not_a_tuple.value.code == "entity-graph-invalid-root"

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
# Member and value validation.                                                 #
# --------------------------------------------------------------------------- #


def test_an_undeclared_member_identity_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, (EntityAttributeInput(_attr(_ORDER, "nosuch"), 1),), (), ())
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


def test_two_entries_for_one_member_are_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, (*_ORDER_SCALARS, _ORDER_SCALARS[0]), (), ())
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


def test_a_null_on_a_non_nullable_attribute_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, (EntityAttributeInput(_attr(_ORDER, "name"), None),), (), ())
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
            order, (EntityAttributeInput(_attr(_ORDER, "orderedOn"), "2024-01-01"),), (), ()
        )
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_to_many_direction_refuses_a_to_one_arm() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(
            order,
            _ORDER_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ORDER, "items"), LOADED_NULL),),
        )
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_to_one_direction_refuses_a_loaded_many_arm() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        item = writer.allocate(_ITEM)
        writer.populate(
            item,
            _ITEM_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ITEM, "order"), LoadedMany(())),),
        )
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_value_that_is_no_relationship_arm_at_all_is_refused() -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        item = writer.allocate(_ITEM)
        writer.populate(
            item,
            _ITEM_SCALARS,
            (),
            (EntityRelationshipInput(_rel(_ITEM, "order"), cast("Any", None)),),
        )
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-value"


# --------------------------------------------------------------------------- #
# Recursive Value Object construction.                                         #
# --------------------------------------------------------------------------- #

_STATUS = sm.SnapOrderStatus.identity
_PRIMARY_TAG = ValueObjectIdentity(_STATUS, ("primaryTag",))
_TAGS = ValueObjectIdentity(_STATUS, ("tags",))
_NESTED_DETAIL = ValueObjectIdentity(_STATUS, ("primaryTag", "detail"))

_STATUS_SCALARS: tuple[EntityAttributeInput, ...] = (
    EntityAttributeInput(_attr(_STATUS, "id"), 21),
    EntityAttributeInput(_attr(_STATUS, "orderId"), 1),
    EntityAttributeInput(_attr(_STATUS, "orderItemId"), None),
    EntityAttributeInput(_attr(_STATUS, "code"), "SHIPPED"),
)


def _tag(
    label: str,
    *,
    occurrence: ValueObjectIdentity = _PRIMARY_TAG,
    nested: ValueObjectOccurrenceInput | None = None,
) -> ValueObjectRecord:
    return ValueObjectRecord(
        attributes=(
            ValueObjectAttributeInput(ValueObjectAttributeIdentity(occurrence, "label"), label),
        ),
        value_objects=() if nested is None else (nested,),
    )


def _status(
    *occurrences: ValueObjectOccurrenceInput,
) -> Any:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        status = writer.allocate(_STATUS)
        writer.populate(status, _STATUS_SCALARS, occurrences, ())
        return (status,)

    return build


def test_a_value_object_occurrence_builds_a_frozen_instance() -> None:
    (root,) = _construct(_status(ValueObjectOccurrenceInput(_PRIMARY_TAG, _tag("urgent"))))
    tag = cast("Any", root).primary_tag
    assert isinstance(tag, sm.Tag)
    assert tag.label == "urgent"
    # An omitted nested occurrence reads as absent at every depth: `None` for a
    # One, the empty tuple for a Many.
    assert tag.detail is None
    assert tag.details == ()


def test_a_nested_occurrence_builds_recursively_in_declaration_order() -> None:
    nested = ValueObjectOccurrenceInput(
        _NESTED_DETAIL,
        ValueObjectRecord(
            attributes=(
                ValueObjectAttributeInput(
                    ValueObjectAttributeIdentity(_NESTED_DETAIL, "note"), "handled"
                ),
            )
        ),
    )
    (root,) = _construct(
        _status(ValueObjectOccurrenceInput(_PRIMARY_TAG, _tag("x", nested=nested)))
    )
    assert cast("Any", root).primary_tag.detail.note == "handled"


def test_a_many_occurrence_preserves_its_record_order() -> None:
    (root,) = _construct(
        _status(
            ValueObjectOccurrenceInput(
                _TAGS,
                (_tag("first", occurrence=_TAGS), _tag("second", occurrence=_TAGS)),
            )
        )
    )
    assert [tag.label for tag in cast("Any", root).tags] == ["first", "second"]


def test_a_many_occurrence_refuses_anything_but_an_exact_tuple() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(
            _status(ValueObjectOccurrenceInput(_TAGS, cast("Any", [_tag("x", occurrence=_TAGS)])))
        )
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_value_object_leaf_outside_its_declared_type_is_refused() -> None:
    record = ValueObjectRecord(
        attributes=(
            ValueObjectAttributeInput(ValueObjectAttributeIdentity(_PRIMARY_TAG, "label"), 7),
        )
    )
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(ValueObjectOccurrenceInput(_PRIMARY_TAG, record)))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_raw_document_mapping_never_crosses_the_construction_seam() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(ValueObjectOccurrenceInput(_PRIMARY_TAG, cast("Any", {"label": "x"}))))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_many_occurrence_is_never_null() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        _construct(_status(ValueObjectOccurrenceInput(_TAGS, cast("Any", None))))
    assert refusal.value.code == "entity-graph-invalid-value"


def test_a_null_one_occurrence_is_the_documents_own_absent_state() -> None:
    # A One occurrence absent from the document, stored as JSON null, or stored
    # in the wrong kind all reach construction as `None`, because the read seam
    # already collapsed them into one not-present state. Re-deriving a
    # nullability verdict here would contradict that collapse.
    (root,) = _construct(_status(ValueObjectOccurrenceInput(_PRIMARY_TAG, None)))
    assert cast("Any", root).primary_tag is None


# --------------------------------------------------------------------------- #
# Lifecycle state: ordering, resolution scope, and atomic publication.         #
# --------------------------------------------------------------------------- #


def _two_nodes(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
    order = writer.allocate(_ORDER)
    item = writer.allocate(_ITEM)
    writer.populate(
        order,
        _ORDER_SCALARS,
        (),
        (EntityRelationshipInput(_rel(_ORDER, "items"), LoadedMany((item,))),),
    )
    writer.populate(
        item,
        _ITEM_SCALARS,
        (),
        (EntityRelationshipInput(_rel(_ITEM, "order"), LoadedOne(order)),),
    )
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
        writer.populate(handle, _ORDER_SCALARS, (), ())
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
    assert entity_runtime_of(_ORDERS) is entity_runtime_of(_ORDERS)
    assert entity_runtime_of(_ORDERS) is not entity_runtime_of(sm.ANIMAL_MODEL)


# --------------------------------------------------------------------------- #
# The closed code set, and the carrier rules the collaboration states in it.   #
# --------------------------------------------------------------------------- #


def test_the_code_set_is_closed_against_an_unlisted_code() -> None:
    assert len(GRAPH_CONSTRUCTION_CODES) == 9
    assert all(code.startswith("entity-graph-") for code in GRAPH_CONSTRUCTION_CODES)
    with pytest.raises(ValueError, match="not a graph construction code"):
        GraphConstructionError(code="entity-graph-nosuch", message="invented")


def test_a_model_that_composed_no_entity_class_can_construct_no_graph() -> None:
    descriptor_backed = DomainModel._from_unresolved(_ClasslessSource())  # pyright: ignore[reportPrivateUsage] - the model's private descriptor-frontend seam

    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        writer.allocate(_ORDER)
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        entity_runtime_of(descriptor_backed).construct(build)
    assert refusal.value.code == "entity-graph-invalid-entity"


@pytest.mark.parametrize(
    "entries",
    [
        pytest.param([EntityAttributeInput(_attr(_ORDER, "id"), 1)], id="an-abstract-sequence"),
        pytest.param(("id",), id="a-wrong-carrier-type"),
    ],
)
def test_only_an_exact_tuple_of_the_declared_carrier_crosses_the_seam(entries: Any) -> None:
    def build(writer: EntityGraphWriter) -> tuple[NodeHandle, ...]:
        order = writer.allocate(_ORDER)
        writer.populate(order, entries, (), ())
        raise AssertionError("unreachable")

    with pytest.raises(GraphConstructionError) as refusal:
        _construct(build)
    assert refusal.value.code == "entity-graph-invalid-member"


def test_an_omitted_value_object_leaf_reads_as_absent_rather_than_failing() -> None:
    # `Tag.label` is required, yet a document that omits it decoded to `None`
    # before construction saw it — the read seam's own absence collapse. The
    # frozen Value Object carries the member as absent, and construction neither
    # invents a value nor re-judges the collapse.
    (root,) = _construct(_status(ValueObjectOccurrenceInput(_PRIMARY_TAG, ValueObjectRecord())))
    tag = cast("Any", root).primary_tag
    assert tag.label is None
    assert "label" not in tag.model_fields_set
