"""The advanced Entity Graph Construction collaboration
(``parallax.core.entity._graph_construction``): the node-indexed graph that
crosses its door, the allocate-before-fill order that closes cycles, the node
index every refusal reads back, and the lifecycle states attached all or none —
which is the whole of that atomicity, since a callback that keeps the instances
it was handed keeps them.

Driven directly rather than through Snapshot, because the contract is the graph
a caller gives — never "the query result".

Every row here is written as a literal tuple against the exact Entity's member
layout, rather than assembled from that layout by name. A row assembled from the
layout would agree with construction however either end drifted; a literal one
is what makes the alignment between the two a thing this suite can be wrong
about.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import warnings
from collections.abc import Callable, Iterator, Sequence
from decimal import Decimal
from typing import Any, cast

import pytest

from parallax.core import Attr, Bitemporal, attr
from parallax.core.base import INFINITY
from parallax.core.entity import (
    UNLOADED,
    GraphConstructionError,
    lifecycle_state_of,
    relationship_value_of,
)
from parallax.core.entity._construction_input import ABSENT
from parallax.core.entity._errors import GRAPH_CONSTRUCTION_CODES
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import DomainModel, model_of
from parallax.core.metamodel import (
    EntityIdentity,
    RelationshipIdentity,
)
from tests._support import snapshot_models as sm
from tests._support.model_capabilities import graph_construction_for
from tests.unit._indexed_graph_support import (
    LiteralGraph,
    Node,
    literal_graph,
    published,
    published_nodes,
)

_ORDERS = sm.SNAP_ORDERS_MODEL
_ORDER = sm.SnapOrder.identity
_ITEM = sm.SnapOrderItem.identity


def _rel(entity: EntityIdentity, name: str) -> RelationshipIdentity:
    return RelationshipIdentity(entity, name)


# `SnapOrder`: id, name, sku, qty, price, active, orderedOn — then items, statuses.
_ORDER_MEMBERS: tuple[object, ...] = (1, "Ada", None, 1, Decimal("1.00"), True, dt.date(2024, 1, 1))
_ORDER_UNLOADED: tuple[object, ...] = (UNLOADED, UNLOADED)

# `SnapOrderItem`: id, orderId, sku, quantity, shippedOn — then order, statuses.
_ITEM_MEMBERS: tuple[object, ...] = (11, 1, "x", 1, None)
_ITEM_UNLOADED: tuple[object, ...] = (UNLOADED, UNLOADED)

_ONE_ORDER: Node = (_ORDER, _ORDER_MEMBERS, _ORDER_UNLOADED)


def _refused(*nodes: Node, model: DomainModel = _ORDERS) -> GraphConstructionError:
    with pytest.raises(GraphConstructionError) as refusal:
        published(model, *nodes)
    return refusal.value


class _CallerDefinedTuple(tuple[Any, ...]):
    """A caller-defined collection subtype: a ``tuple`` for ``isinstance``, and
    still not the exact built-in the seams take."""


# --------------------------------------------------------------------------- #
# Allocation, filling, and the cycle allocating first exists for.              #
# --------------------------------------------------------------------------- #


def test_publish_answers_node_0_as_a_frozen_instance_of_the_composed_class() -> None:
    root = published(_ORDERS, _ONE_ORDER)
    assert isinstance(root, sm.SnapOrder)
    assert (root.id, root.name, root.qty) == (1, "Ada", 1)
    assert root.sku is None


def test_every_node_is_allocated_before_any_is_filled_so_a_cycle_closes() -> None:
    root = cast(
        "sm.SnapOrder",
        published(
            _ORDERS,
            (_ORDER, _ORDER_MEMBERS, ((1,), UNLOADED)),
            (_ITEM, _ITEM_MEMBERS, (0, UNLOADED)),
        ),
    )
    assert root.items[0].order is root


def test_a_node_reached_from_two_positions_is_one_instance() -> None:
    order, first, second = published_nodes(
        _ORDERS,
        (_ORDER, _ORDER_MEMBERS, ((1, 2, 1), UNLOADED)),
        (_ITEM, _ITEM_MEMBERS, (0, UNLOADED)),
        (_ITEM, (12, 1, "y", 2, None), (0, UNLOADED)),
    )
    assert cast("sm.SnapOrder", order).items == (first, second, first)


def test_each_publication_creates_fresh_instances() -> None:
    construction = graph_construction_for(_ORDERS)
    first = published(construction, _ONE_ORDER)
    second = published(construction, _ONE_ORDER)
    assert first is not second
    assert first == second


def test_an_unloaded_relationship_value_installs_the_closed_world_sentinel() -> None:
    root = published(_ORDERS, _ONE_ORDER)
    assert relationship_value_of(root, _rel(_ORDER, "items")) is UNLOADED
    assert relationship_value_of(root, _rel(_ORDER, "statuses")) is UNLOADED


def test_loaded_null_and_loaded_empty_stay_distinct_from_unloaded() -> None:
    order, item = published_nodes(
        _ORDERS,
        (_ORDER, _ORDER_MEMBERS, ((), UNLOADED)),
        (_ITEM, _ITEM_MEMBERS, (None, UNLOADED)),
    )
    assert cast("sm.SnapOrder", order).items == ()
    assert cast("sm.SnapOrderItem", item).order is None
    assert relationship_value_of(order, _rel(_ORDER, "statuses")) is UNLOADED


def test_an_absent_member_position_leaves_its_declared_default_in_place() -> None:
    # A positional row cannot omit, so absence is a value at the position. The
    # member is never written, so it reads back as its declared default and its
    # presence bit stays clear: `model_fields_set` answers from that bitmap.
    order = cast(
        "sm.SnapOrder",
        published(
            _ORDERS, (_ORDER, (1, "Ada", ABSENT, ABSENT, ABSENT, ABSENT, ABSENT), _ORDER_UNLOADED)
        ),
    )
    assert (order.id, order.name) == (1, "Ada")
    assert order.sku is None
    assert order.model_fields_set == {"id", "name"}


# --------------------------------------------------------------------------- #
# The graph and its layouts.                                                   #
# --------------------------------------------------------------------------- #


def test_an_empty_graph_is_refused_because_it_has_no_root() -> None:
    refusal = _refused()
    assert refusal.code == "entity-graph-invalid-value"
    assert refusal.index is None


def test_a_node_of_an_entity_the_model_composed_no_class_for_is_refused() -> None:
    construction = graph_construction_for(_ORDERS)
    foreign = graph_construction_for(sm.ANIMAL_MODEL).cataloged.layouts.entity(sm.Cat.identity)
    graph = literal_graph(construction, _ONE_ORDER)
    graph = LiteralGraph(
        (*graph.layouts, foreign), (*graph.members, ()), (*graph.relationships, ())
    )
    with pytest.raises(GraphConstructionError) as refusal:
        construction.publish(graph, _no_states)
    assert refusal.value.code == "entity-graph-invalid-entity"
    assert (refusal.value.index, refusal.value.identity) == (1, sm.Cat.identity)


def test_a_layout_this_model_does_not_lay_its_entity_out_by_is_refused() -> None:
    construction = graph_construction_for(_ORDERS)
    graph = literal_graph(construction, _ONE_ORDER)
    other = dataclasses.replace(graph.layouts[0], relationships=())
    with pytest.raises(GraphConstructionError) as refusal:
        construction.publish(LiteralGraph((other,), graph.members, graph.relationships), _no_states)
    assert refusal.value.code == "entity-graph-layout-mismatch"
    assert (refusal.value.index, refusal.value.identity) == (0, _ORDER)


def test_a_node_answering_no_layout_at_all_is_refused_as_a_mismatch() -> None:
    construction = graph_construction_for(_ORDERS)
    graph = literal_graph(construction, _ONE_ORDER)
    with pytest.raises(GraphConstructionError) as refusal:
        construction.publish(
            LiteralGraph((cast("Any", _ORDER),), graph.members, graph.relationships), _no_states
        )
    assert refusal.value.code == "entity-graph-layout-mismatch"
    assert refusal.value.index == 0


def test_an_equal_layout_from_another_catalog_of_one_model_is_accepted() -> None:
    # Layouts are pure functions of the accepted model, so nothing compares one
    # by identity: an interchangeable catalog lays the same rows out.
    construction = graph_construction_for(_ORDERS)
    graph = literal_graph(construction, _ONE_ORDER)
    twin = CatalogedModel(model_of(_ORDERS)).layouts.entity(_ORDER)
    assert twin is not graph.layouts[0]
    root = construction.publish(
        LiteralGraph((twin,), graph.members, graph.relationships), _no_states
    )
    assert isinstance(root, sm.SnapOrder)


def test_an_exception_a_graph_accessor_raises_propagates_unchanged() -> None:
    class _Boom(RuntimeError):
        pass

    class _Failing(LiteralGraph):
        def relationship_values(self, node: int) -> Any:
            raise _Boom(f"the caller's own failure at {node}")

    construction = graph_construction_for(_ORDERS)
    graph = literal_graph(construction, _ONE_ORDER)
    with pytest.raises(_Boom, match="the caller's own failure at 0"):
        construction.publish(
            _Failing(graph.layouts, graph.members, graph.relationships), _no_states
        )


def _no_states(instances: Sequence[object]) -> list[object]:
    return [None] * len(instances)


# --------------------------------------------------------------------------- #
# Row shape, row width, and value validation.                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "members",
    [
        pytest.param((*_ORDER_MEMBERS, 1), id="one-position-too-many"),
        pytest.param(_ORDER_MEMBERS[:-1], id="one-position-too-few"),
        pytest.param((), id="no-positions-at-all"),
        pytest.param(list(_ORDER_MEMBERS), id="an-abstract-sequence"),
        pytest.param(_CallerDefinedTuple(_ORDER_MEMBERS), id="a-caller-defined-collection-subtype"),
        pytest.param("idnamesku", id="a-value-that-is-no-row-at-all"),
    ],
)
def test_a_member_row_that_is_not_an_exact_tuple_of_the_layout_width_is_refused(
    members: Any,
) -> None:
    # Width is the whole membership check a positional row needs. A position
    # names one declared member and nothing else, so an undeclared member has no
    # position to occupy and a duplicate has one position to occupy. What is left
    # to refuse is a row of any other width or kind.
    refusal = _refused(_ONE_ORDER, (_ORDER, members, _ORDER_UNLOADED))
    assert refusal.code == "entity-graph-invalid-member"
    assert (refusal.index, refusal.identity) == (1, _ORDER)


@pytest.mark.parametrize(
    "relationships",
    [
        pytest.param((UNLOADED,), id="one-position-too-few"),
        pytest.param((UNLOADED, UNLOADED, UNLOADED), id="one-position-too-many"),
        pytest.param([UNLOADED, UNLOADED], id="an-abstract-sequence"),
        pytest.param(
            _CallerDefinedTuple((UNLOADED, UNLOADED)), id="a-caller-defined-collection-subtype"
        ),
    ],
)
def test_a_relationship_row_that_is_not_an_exact_tuple_of_the_layout_width_is_refused(
    relationships: Any,
) -> None:
    refusal = _refused((_ORDER, _ORDER_MEMBERS, relationships))
    assert refusal.code == "entity-graph-invalid-member"
    assert refusal.index == 0


def test_construction_does_not_rejudge_attribute_nullability() -> None:
    # Member rows are already-judged Entity State. Graph Construction installs
    # their values without recreating the admission decision at this later seam.
    root = published(
        _ORDERS, (_ORDER, (1, None, ABSENT, ABSENT, ABSENT, ABSENT, ABSENT), _ORDER_UNLOADED)
    )
    assert cast("sm.SnapOrder", root).name is None


def test_construction_does_not_rejudge_an_attribute_neutral_type() -> None:
    # The producer of Entity State owns scalar admission. Construction bypasses
    # Pydantic validation deliberately and preserves that earlier judgment rather
    # than claiming a second source-data boundary.
    root = published(
        _ORDERS,
        (_ORDER, (1, "Ada", ABSENT, ABSENT, ABSENT, ABSENT, "2024-01-01"), _ORDER_UNLOADED),
    )
    assert cast("sm.SnapOrder", root).ordered_on == "2024-01-01"


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(None, id="loaded-null"),
        pytest.param(1, id="one-node"),
        pytest.param([1], id="a-mutable-collection"),
        pytest.param(_CallerDefinedTuple((1,)), id="a-caller-defined-collection-subtype"),
    ],
)
def test_a_to_many_direction_takes_only_an_exact_tuple_of_node_indices(value: object) -> None:
    refusal = _refused(
        (_ORDER, _ORDER_MEMBERS, (value, UNLOADED)), (_ITEM, _ITEM_MEMBERS, _ITEM_UNLOADED)
    )
    assert refusal.code == "entity-graph-invalid-value"
    assert (refusal.index, refusal.identity) == (0, _rel(_ORDER, "items"))


def test_a_to_one_direction_refuses_a_tuple_of_node_indices() -> None:
    refusal = _refused(_ONE_ORDER, (_ITEM, _ITEM_MEMBERS, ((0,), UNLOADED)))
    assert refusal.code == "entity-graph-invalid-value"
    assert (refusal.index, refusal.identity) == (1, _rel(_ITEM, "order"))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param(2, id="past-the-last-node"),
        pytest.param(-1, id="a-negative-index"),
        pytest.param(True, id="a-bool"),
        pytest.param("0", id="no-index-at-all"),
    ],
)
def test_a_to_one_value_naming_no_node_of_the_graph_is_refused(value: object) -> None:
    refusal = _refused(_ONE_ORDER, (_ITEM, _ITEM_MEMBERS, (value, UNLOADED)))
    assert refusal.code == "entity-graph-invalid-value"
    assert (refusal.index, refusal.identity) == (1, _rel(_ITEM, "order"))


@pytest.mark.parametrize(
    "value",
    [
        pytest.param((1, 2), id="past-the-last-node"),
        pytest.param((1, -1), id="a-negative-index"),
        pytest.param((1.0,), id="no-index-at-all"),
    ],
)
def test_a_to_many_value_naming_no_node_of_the_graph_is_refused(value: object) -> None:
    refusal = _refused(
        (_ORDER, _ORDER_MEMBERS, (value, UNLOADED)), (_ITEM, _ITEM_MEMBERS, _ITEM_UNLOADED)
    )
    assert refusal.code == "entity-graph-invalid-value"
    assert (refusal.index, refusal.identity) == (0, _rel(_ORDER, "items"))


# --------------------------------------------------------------------------- #
# Recursive Value Object construction.                                         #
# --------------------------------------------------------------------------- #

_STATUS = sm.SnapOrderStatus.identity

# `SnapOrderStatus`: id, orderId, orderItemId, code — then primaryTag, tags.
# A `Tag` member row is label, detail, details.
_STATUS_MEMBERS: tuple[object, ...] = (21, 1, None, "SHIPPED", ABSENT, ABSENT)


def _tag(label: object, *, detail: object = ABSENT, details: object = ABSENT) -> tuple[object, ...]:
    return (label, detail, details)


def _status(*, primary: object = ABSENT, tags: object = ABSENT) -> Node:
    return (_STATUS, (*_STATUS_MEMBERS[:4], primary, tags), ())


def test_a_value_object_occurrence_builds_a_frozen_instance() -> None:
    tag = published(_ORDERS, _status(primary=_tag("urgent"))).primary_tag
    assert isinstance(tag, sm.Tag)
    assert tag.label == "urgent"
    # An absent nested occurrence reads as absent at every depth: `None` for a
    # One, the empty tuple for a Many.
    assert tag.detail is None
    assert tag.details == ()


def test_a_nested_occurrence_builds_recursively_in_declaration_order() -> None:
    root = published(_ORDERS, _status(primary=_tag("x", detail=("handled",))))
    assert root.primary_tag.detail.note == "handled"


def test_a_many_occurrence_preserves_its_record_order() -> None:
    root = published(_ORDERS, _status(tags=(_tag("first"), _tag("second"))))
    assert [tag.label for tag in root.tags] == ["first", "second"]


@pytest.mark.parametrize(
    "collection",
    [
        pytest.param(list, id="a-mutable-collection"),
        pytest.param(_CallerDefinedTuple, id="a-caller-defined-collection-subtype"),
    ],
)
def test_a_many_occurrence_refuses_anything_but_an_exact_tuple(collection: Any) -> None:
    refusal = _refused(_status(tags=collection((_tag("x"),))))
    assert refusal.code == "entity-graph-invalid-value"


@pytest.mark.parametrize(
    "row",
    [
        pytest.param(("x", ABSENT, ABSENT, ABSENT), id="one-position-too-many"),
        pytest.param(("x", ABSENT), id="one-position-too-few"),
    ],
)
def test_a_value_object_member_row_of_the_wrong_width_is_refused(row: Any) -> None:
    refusal = _refused(_status(primary=row))
    assert refusal.code == "entity-graph-invalid-value"


def test_construction_does_not_rejudge_a_value_object_scalar() -> None:
    assert published(_ORDERS, _status(primary=_tag(7))).primary_tag.label == 7


def test_a_raw_document_mapping_never_crosses_the_construction_seam() -> None:
    refusal = _refused(_status(primary={"label": "x"}))
    assert refusal.code == "entity-graph-invalid-value"


def test_a_many_occurrence_is_never_null() -> None:
    refusal = _refused(_status(tags=None))
    assert refusal.code == "entity-graph-invalid-value"


def test_a_refusal_at_any_value_object_depth_names_the_node_whose_row_holds_it() -> None:
    # The node index a refusal reads back is the owning node's even when the
    # refused value sits inside a nested occurrence's own row.
    refusal = _refused(_status(), _status(primary=_tag("x", details=[_tag("y")])))
    assert refusal.code == "entity-graph-invalid-value"
    assert refusal.index == 1
    assert cast("Any", refusal.identity).path == ("primaryTag", "details")


def test_publication_resolves_no_class_facts_per_record(monkeypatch: pytest.MonkeyPatch) -> None:
    # Correspondence proves each occurrence path's class and plan once per
    # model, so publishing a record at any depth looks neither up again.
    from parallax.core.entity import _graph_construction, _row_fill

    construction = graph_construction_for(_ORDERS)

    def refuse(*_args: object) -> Any:
        raise AssertionError("a per-record class-fact lookup")

    for module in (_graph_construction, _row_fill):
        for name in ("plan_of", "shape_of", "wire_names_of"):
            monkeypatch.setattr(module, name, refuse, raising=False)

    status = published(
        construction,
        _status(
            primary=_tag("x", detail=("handled",), details=(("a",), ("b",))),
            tags=(_tag("first"), _tag("second", details=())),
        ),
    )
    assert status.primary_tag.detail.note == "handled"
    assert [detail.note for detail in status.primary_tag.details] == ["a", "b"]
    assert [tag.label for tag in status.tags] == ["first", "second"]


def test_a_null_one_occurrence_is_the_documents_own_absent_state() -> None:
    # A One occurrence absent from the document, stored as JSON null, or stored
    # in the wrong kind all reach construction as `None`, because the read seam
    # already collapsed them into one not-present state. Re-deriving a
    # nullability verdict here would contradict that collapse.
    assert published(_ORDERS, _status(primary=None)).primary_tag is None


def test_an_absent_value_object_scalar_reads_as_absent_rather_than_failing() -> None:
    # `Tag.label` is required, yet a document that omits it decoded to `ABSENT`
    # before construction saw it — the read seam's own absence collapse. The
    # frozen Value Object carries the member as absent, and construction neither
    # invents a value nor re-judges the collapse.
    tag = published(_ORDERS, _status(primary=_tag(ABSENT))).primary_tag
    assert tag.label is None
    assert "label" not in tag.model_fields_set


def test_an_absent_scalar_inside_a_many_element_reads_as_absent_too() -> None:
    # Absence is per element, not per occurrence: an element of a Many carries the
    # same distinction its One sibling does, so re-serializing the collection
    # never spells an omission the element never held as an explicit null.
    absent, named = published(_ORDERS, _status(tags=(_tag(ABSENT), _tag("named")))).tags
    assert absent.label is None
    assert "label" not in absent.model_fields_set
    assert named.label == "named"
    assert "label" in named.model_fields_set


# --------------------------------------------------------------------------- #
# Native infinity in already-judged temporal state.                            #
# --------------------------------------------------------------------------- #


class _Milestone(Bitemporal, table="graph_milestone", name="Milestone", namespace="parallax.test"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[Decimal] = attr(precision=18, scale=2)


_MILESTONES = DomainModel(_Milestone)
_MILESTONE = _Milestone.identity

# `_Milestone`: id, amount, validStart, validEnd, txStart, txEnd — no relationships.
_MILESTONE_BOUNDS: tuple[str, ...] = ("validStart", "validEnd", "txStart", "txEnd")


def _bound(name: str) -> Any:
    return published(
        _MILESTONES,
        (
            _MILESTONE,
            (
                1,
                Decimal("1.00"),
                *(INFINITY if bound == name else ABSENT for bound in _MILESTONE_BOUNDS),
            ),
            (),
        ),
    )


@pytest.mark.parametrize("name", ["txEnd", "validEnd"])
def test_a_temporal_end_attribute_carries_the_open_upper_bound(name: str) -> None:
    assert getattr(_bound(name), "tx_end" if name == "txEnd" else "valid_end") is INFINITY


@pytest.mark.parametrize("name", ["txStart", "validStart"])
def test_construction_does_not_rejudge_a_temporal_start(name: str) -> None:
    # Temporal-end admission belongs to snapshot materialization. At this lower
    # seam every endpoint is already-judged Entity State and is installed as-is.
    assert getattr(_bound(name), "tx_start" if name == "txStart" else "valid_start") is INFINITY


# --------------------------------------------------------------------------- #
# Publishing a subtype, where a member's declaring class is not the published  #
# one: what a member the read did not carry reads back as, and dumps as.       #
# --------------------------------------------------------------------------- #

_CAT = sm.Cat.identity

# `Cat`: id, name, ownerId (Animal's), licenseId (Pet's), indoor (Cat's own).
_CAT_UNCARRIED: tuple[object, ...] = (1, "Tom", ABSENT, ABSENT, ABSENT)


def _cat(members: tuple[object, ...]) -> Any:
    return published(sm.ANIMAL_MODEL, (_CAT, members, ()))


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
# Lifecycle states: one call, every state buffered, all attached or none.      #
# --------------------------------------------------------------------------- #

_TWO_NODES: tuple[Node, ...] = (
    (_ORDER, _ORDER_MEMBERS, ((1,), UNLOADED)),
    (_ITEM, _ITEM_MEMBERS, (0, UNLOADED)),
)


def _publish_two(lifecycle_states: Any) -> object:
    construction = graph_construction_for(_ORDERS)
    return construction.publish(literal_graph(construction, *_TWO_NODES), lifecycle_states)


def test_lifecycle_states_are_answered_once_for_every_instance_in_node_order() -> None:
    calls: list[tuple[type, ...]] = []

    def lifecycle_states(instances: Sequence[object]) -> tuple[object, ...]:
        calls.append(tuple(type(instance) for instance in instances))
        return ("order state", "item state")

    root = cast("sm.SnapOrder", _publish_two(lifecycle_states))
    assert calls == [(sm.SnapOrder, sm.SnapOrderItem)]
    assert lifecycle_state_of(root) == "order state"
    assert lifecycle_state_of(root.items[0]) == "item state"


def test_the_callback_sees_every_instance_filled_and_wired_and_none_stateful() -> None:
    seen: list[object] = []

    def lifecycle_states(instances: Sequence[object]) -> list[object]:
        order, item = (cast("Any", instance) for instance in instances)
        assert order.items[0] is item
        assert item.order is order
        assert [lifecycle_state_of(instance) for instance in instances] == [None, None]
        seen.extend(instances)
        return ["state", "state"]

    root = _publish_two(lifecycle_states)
    assert seen[0] is root


def test_a_lazily_produced_sequence_of_the_right_length_is_accepted() -> None:
    def lifecycle_states(instances: Sequence[object]) -> Any:
        return (f"state {node}" for node in range(len(instances)))

    root = cast("sm.SnapOrder", _publish_two(lifecycle_states))
    assert lifecycle_state_of(root.items[0]) == "state 1"


def _kept_and_refused(
    lifecycle_states: Callable[[Sequence[object]], object],
) -> tuple[list[object], BaseException]:
    kept: list[object] = []

    def keeping(instances: Sequence[object]) -> object:
        kept.extend(instances)
        return lifecycle_states(instances)

    with pytest.raises(BaseException) as refusal:
        _publish_two(keeping)
    return kept, refusal.value


def test_a_callback_exception_propagates_unchanged_and_attaches_no_state() -> None:
    class _Boom(RuntimeError):
        pass

    def lifecycle_states(instances: Sequence[object]) -> object:
        raise _Boom("the lifecycle's own failure")

    kept, refusal = _kept_and_refused(lifecycle_states)
    assert type(refusal) is _Boom
    assert [lifecycle_state_of(node) for node in kept] == [None, None]


@pytest.mark.parametrize(
    "states", [pytest.param(("one",), id="short"), pytest.param(("a", "b", "c"), id="long")]
)
def test_a_state_count_other_than_the_node_count_attaches_none(states: tuple[str, ...]) -> None:
    kept, refusal = _kept_and_refused(lambda _instances: states)
    assert isinstance(refusal, GraphConstructionError)
    assert (refusal.code, refusal.index) == ("entity-graph-invalid-value", None)
    assert [lifecycle_state_of(node) for node in kept] == [None, None]


def test_states_failing_while_being_consumed_attach_none() -> None:
    def failing() -> Iterator[object]:
        yield "order state"
        raise LookupError("the second state failed")

    kept, refusal = _kept_and_refused(lambda _instances: failing())
    assert type(refusal) is LookupError
    assert [lifecycle_state_of(node) for node in kept] == [None, None]


def test_an_instance_a_failed_callback_kept_is_still_filled_and_still_state_free() -> None:
    # The input that breaks the obvious summary of the atomicity, so the summary
    # is not what this suite grades. The callback is handed the FINAL instances,
    # so a callback that keeps them still holds them after publication fails,
    # fully filled and no less reachable for the failure. Nothing here can take
    # them back; what the failure does guarantee is that no root is answered and
    # no node carries lifecycle state.
    def lifecycle_states(_instances: Sequence[object]) -> object:
        raise RuntimeError("the lifecycle fails")

    kept, _ = _kept_and_refused(lifecycle_states)
    order, item = (cast("Any", node) for node in kept)
    assert (order.name, order.qty) == ("Ada", 1)
    assert (item.id, item.sku) == (11, "x")
    assert relationship_value_of(order, _rel(_ORDER, "items")) == (item,)
    assert [lifecycle_state_of(node) for node in kept] == [None, None]


def test_reading_a_relationship_the_class_family_does_not_declare_is_refused() -> None:
    root = published(_ORDERS, _ONE_ORDER)
    with pytest.raises(GraphConstructionError) as refusal:
        relationship_value_of(root, _rel(_ORDER, "nosuch"))
    assert refusal.value.code == "entity-graph-invalid-member"


def test_a_construction_derives_every_declared_entity_at_construction() -> None:
    construction = graph_construction_for(_ORDERS)
    derived = construction._facts  # pyright: ignore[reportPrivateUsage] - the derivation is the claim
    assert set(derived) == {entity.identity for entity in _ORDERS.entities}


def test_an_entity_the_model_does_not_declare_is_refused_at_lookup() -> None:
    with pytest.raises(GraphConstructionError) as refusal:
        graph_construction_for(_ORDERS).facts_for(sm.Cat.identity)
    assert refusal.value.code == "entity-graph-invalid-entity"
    assert refusal.value.identity == sm.Cat.identity


# --------------------------------------------------------------------------- #
# The closed code set.                                                         #
# --------------------------------------------------------------------------- #


# The four closed codes are restated here rather than imported so a code added,
# renamed, or dropped on either side fails instead of agreeing with itself.
_SPEC_CODES = frozenset(
    {
        "entity-graph-invalid-entity",
        "entity-graph-invalid-member",
        "entity-graph-invalid-value",
        "entity-graph-layout-mismatch",
    }
)


def test_the_code_set_is_closed_against_an_unlisted_code() -> None:
    assert GRAPH_CONSTRUCTION_CODES == _SPEC_CODES
    with pytest.raises(ValueError, match="not a graph construction code"):
        GraphConstructionError(code="entity-graph-nosuch", message="invented")
