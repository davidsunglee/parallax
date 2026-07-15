"""Deep-fetch pure planner unit tests (m-deep-fetch).

Exercises `parallax.core.deep_fetch.plan` independently of the Docker-gated
compile/run sweeps: shared-prefix dedup, broad-vs-narrowed distinct hops,
equivalent-narrowing convergence, the `1 + L` accounting, child-operation
composition (`in` membership + propagated as-of + declared relationship
`orderBy`), narrowed view-key derivation, and back-reference (ancestor-revisit)
cycle detection. The planner never compiles or executes anything — every
assertion here is over the returned `FetchPlan` / `FetchLevel` shape alone.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import deep_fetch
from parallax.core.descriptor import Metamodel
from parallax.core.op_algebra import (
    All,
    And,
    AsOf,
    Comparison,
    DeepFetch,
    Membership,
    Narrow,
    Operation,
    OrderBy,
    PathSegment,
)

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
ANIMAL = _MODELS["animal"]
POLICY = _MODELS["policy"]
RATE = _MODELS["rate"]


def _seg(rel: str, narrow: tuple[str, ...] = ()) -> PathSegment:
    return PathSegment(rel=rel, narrow=narrow)


def _plan(
    meta: Metamodel,
    target: str,
    paths: tuple[tuple[PathSegment, ...], ...],
    operand: Operation | None = None,
) -> deep_fetch.FetchPlan:
    op = DeepFetch(operand=operand if operand is not None else All(), paths=paths)
    return deep_fetch.plan(target, op, meta)


# --------------------------------------------------------------------------- #
# Shared-prefix dedup + independent paths (m-deep-fetch dedup identity).       #
# --------------------------------------------------------------------------- #
def test_shared_prefix_dedups_to_one_level() -> None:
    plan = _plan(
        ORDERS,
        "Order",
        ((_seg("Order.items"),), (_seg("Order.items"), _seg("OrderItem.statuses"))),
    )
    assert len(plan.levels) == 2
    items, statuses = plan.levels
    assert items.attach_key == "items"
    assert isinstance(items.parent, deep_fetch.RootRef)
    assert statuses.attach_key == "statuses"
    assert isinstance(statuses.parent, deep_fetch.LevelRef)
    assert statuses.parent.index == 0


def test_two_independent_paths_off_root_are_two_levels_both_rooted() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"),), (_seg("Order.itemsByShipDate"),)))
    assert len(plan.levels) == 2
    assert all(isinstance(level.parent, deep_fetch.RootRef) for level in plan.levels)
    assert {level.attach_key for level in plan.levels} == {"items", "itemsByShipDate"}


def test_multi_hop_path_chains_levels_in_declared_order() -> None:
    plan = _plan(POLICY, "Policy", ((_seg("Policy.coverages"), _seg("Coverage.claims")),))
    assert [level.attach_key for level in plan.levels] == ["coverages", "claims"]
    coverages, claims = plan.levels
    assert isinstance(coverages.parent, deep_fetch.RootRef)
    assert isinstance(claims.parent, deep_fetch.LevelRef)
    assert claims.parent.index == 0


# --------------------------------------------------------------------------- #
# Broad-vs-narrowed distinct hops; equivalent narrowings converge.             #
# --------------------------------------------------------------------------- #
def test_broad_and_narrowed_over_the_same_relationship_are_distinct_levels() -> None:
    plan = _plan(
        ANIMAL,
        "Person",
        ((_seg("Person.pets"),), (_seg("Person.pets", ("Dog",)),)),
    )
    assert len(plan.levels) == 2
    keys = {level.attach_key for level in plan.levels}
    assert keys == {"pets", "pets[Dog]"}


def test_equivalent_narrowings_dedup_to_one_hop() -> None:
    # `to: [Pet]` (the abstract subtype) and `to: [Cat, Dog]` (its own concretes)
    # resolve to the SAME effective set {Cat, Dog} -> the same view key -> ONE level.
    plan = _plan(
        ANIMAL,
        "Person",
        ((_seg("Person.pets", ("Pet",)),), (_seg("Person.pets", ("Cat", "Dog")),)),
    )
    assert len(plan.levels) == 1
    assert plan.levels[0].attach_key == "pets[Cat,Dog]"


def test_two_different_narrow_sets_are_distinct_levels() -> None:
    plan = _plan(
        ANIMAL,
        "Person",
        ((_seg("Person.pets", ("Dog",)),), (_seg("Person.pets", ("Cat",)),)),
    )
    assert len(plan.levels) == 2
    assert {level.attach_key for level in plan.levels} == {"pets[Dog]", "pets[Cat]"}


def test_narrowed_view_key_is_alphabetical_no_spaces() -> None:
    plan = _plan(ANIMAL, "Person", ((_seg("Person.pets", ("Dog", "Cat")),),))
    assert plan.levels[0].attach_key == "pets[Cat,Dog]"


# --------------------------------------------------------------------------- #
# `1 + L` accounting: L counts distinct (post-dedup) hops.                    #
# --------------------------------------------------------------------------- #
def test_l_counts_distinct_hops_after_dedup() -> None:
    # [items], [items, statuses], [itemsByShipDate] -> 3 distinct hops (items,
    # statuses under items, itemsByShipDate) despite 3 declared paths.
    plan = _plan(
        ORDERS,
        "Order",
        (
            (_seg("Order.items"),),
            (_seg("Order.items"), _seg("OrderItem.statuses")),
            (_seg("Order.itemsByShipDate"),),
        ),
    )
    assert len(plan.levels) == 3


def test_narrow_and_broad_both_count_toward_l() -> None:
    plan = _plan(ANIMAL, "Person", ((_seg("Person.animals"),), (_seg("Person.pets", ("Dog",)),)))
    assert len(plan.levels) == 2


# --------------------------------------------------------------------------- #
# Child-operation shape: IN membership + propagated as-of + declared orderBy. #
# --------------------------------------------------------------------------- #
def test_child_operation_is_a_plain_in_membership() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.statuses"),),))
    target, op = plan.levels[0].child_operation([1, 2, 3])
    assert target == "OrderStatus"
    assert isinstance(op, Membership)
    assert op.op == "in"
    assert op.attr == "OrderStatus.orderId"
    assert op.values == (1, 2, 3)


def test_child_operation_wraps_declared_relationship_order_by() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"),),))
    target, op = plan.levels[0].child_operation([1])
    assert target == "OrderItem"
    assert isinstance(op, OrderBy)
    assert op.keys[0].attr == "OrderItem.id"
    assert op.keys[0].direction == "desc"
    assert isinstance(op.operand, Membership)


def test_child_operation_multi_key_order_by_preserves_declared_sequence() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.tags"),),))
    _target, op = plan.levels[0].child_operation([1])
    assert isinstance(op, OrderBy)
    assert [(key.attr, key.direction) for key in op.keys] == [
        ("OrderTag.priority", "desc"),
        ("OrderTag.label", "asc"),
    ]


def test_child_operation_has_no_order_by_when_relationship_declares_none() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.statuses"),),))
    _target, op = plan.levels[0].child_operation([1])
    assert isinstance(op, Membership)  # no OrderBy wrapper at all


def test_child_operation_appends_propagated_as_of_after_the_in_membership() -> None:
    # every axis defaults to latest (the root operand pins none explicitly)
    op = DeepFetch(operand=All(), paths=((_seg("Policy.coverages"),),))
    plan = deep_fetch.plan("Policy", op, POLICY)
    _target, child_op = plan.levels[0].child_operation([1, 2])
    assert isinstance(child_op, And)
    membership, *as_of_terms = child_op.operands
    assert isinstance(membership, Membership)
    assert membership.values == (1, 2)
    assert len(as_of_terms) == 2  # business then processing (AXIS_ORDER)


def test_child_operation_raises_on_a_back_reference_level() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"), _seg("OrderItem.order")),))
    back_reference = plan.levels[1]
    assert back_reference.is_back_reference
    with pytest.raises(deep_fetch.DeepFetchError):
        back_reference.child_operation([1])


# --------------------------------------------------------------------------- #
# Single-concrete narrow bypasses the Narrow node entirely (compile_read's own #
# concrete-target dispatch already yields the correct tag filter, no          #
# projection) — a 2+-concrete resolution DOES wrap Narrow.                    #
# --------------------------------------------------------------------------- #
def test_single_concrete_narrow_targets_the_concrete_directly_no_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", ((_seg("Person.pets", ("Dog",)),),))
    level = plan.levels[0]
    assert level.child_target == "Dog"
    assert level.narrow_to is None
    _target, op = level.child_operation([1])
    assert isinstance(op, Membership)
    assert op.attr == "Dog.ownerId"


def test_multi_concrete_narrow_wraps_a_narrow_node() -> None:
    plan = _plan(ANIMAL, "Person", ((_seg("Person.pets", ("Cat", "Dog")),),))
    level = plan.levels[0]
    assert level.child_target == "Pet"
    assert level.narrow_to == ("Cat", "Dog")
    _target, op = level.child_operation([1])
    assert isinstance(op, Narrow)
    assert op.entity == "Pet"


def test_broad_polymorphic_hop_targets_the_relationship_position_no_narrow() -> None:
    plan = _plan(ANIMAL, "Person", ((_seg("Person.animals"),),))
    level = plan.levels[0]
    assert level.child_target == "Animal"
    assert level.narrow_to is None


def test_non_polymorphic_child_target_is_the_related_entity_itself() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"),),))
    assert plan.levels[0].child_target == "OrderItem"


# --------------------------------------------------------------------------- #
# Back-reference (ancestor-revisit) cycle detection.                          #
# --------------------------------------------------------------------------- #
def test_back_reference_hop_is_detected() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"), _seg("OrderItem.order")),))
    items, order = plan.levels
    assert not items.is_back_reference
    assert order.is_back_reference
    assert order.back_reference_family == "Order"
    assert order.parent_column == "order_id"


def test_ordinary_deeper_level_is_not_flagged_a_back_reference() -> None:
    plan = _plan(ORDERS, "Order", ((_seg("Order.items"), _seg("OrderItem.statuses")),))
    assert not any(level.is_back_reference for level in plan.levels)


def test_a_path_cannot_continue_past_a_back_reference_level() -> None:
    with pytest.raises(deep_fetch.DeepFetchError):
        _plan(
            ORDERS,
            "Order",
            ((_seg("Order.items"), _seg("OrderItem.order"), _seg("Order.items")),),
        )


# --------------------------------------------------------------------------- #
# The planner is pure: no paths means no levels; the root operation is        #
# canonicalized (as-of injected, navigation composed) but nothing executes.   #
# --------------------------------------------------------------------------- #
def test_zero_paths_plans_zero_levels() -> None:
    plan = _plan(ORDERS, "Order", ())
    assert plan.levels == ()


def test_root_operation_is_canonicalized_even_with_zero_paths() -> None:
    literal = Comparison(op="eq", attr="Order.id", value=1)
    op = DeepFetch(operand=literal, paths=())
    plan = deep_fetch.plan("Order", op, ORDERS)
    assert plan.root_operation == literal


def test_plan_accepts_a_non_deep_fetch_operation_with_zero_levels() -> None:
    # A bare read (no DeepFetch wrapper at all) plans as a zero-level fetch —
    # the degenerate "materialize with no relationships" shape a plain snapshot
    # find or a scenario's own `find` step needs.
    literal = Comparison(op="eq", attr="Order.id", value=1)
    plan = deep_fetch.plan("Order", literal, ORDERS)
    assert plan.levels == ()
    assert plan.root_operation == literal


# --------------------------------------------------------------------------- #
# Root as-of injection over a CONCRETE inheritance target whose family's axes  #
# are declared on the ROOT alone (COR-3 Phase 7 review remediation, P3/P4):   #
# `plan()` must inject the default-latest / pinned as-of predicate even       #
# though `DepositRate`'s own record carries no `as_of_attributes` locally.    #
# --------------------------------------------------------------------------- #
def test_concrete_target_root_operation_defaults_every_axis_to_latest() -> None:
    plan = deep_fetch.plan("DepositRate", All(), RATE)
    # Business-axis-first (m-temporal-read), both defaulted to the current
    # milestone since neither axis is pinned: `thru_z = infinity`, `out_z = infinity`.
    assert plan.root_operation == And(
        operands=(
            Comparison(op="eq", attr="Rate.businessTo", value="infinity"),
            Comparison(op="eq", attr="Rate.processingTo", value="infinity"),
        )
    )


def test_concrete_target_root_operation_injects_a_pinned_axis() -> None:
    op = AsOf(
        operand=All(), as_of_attr="DepositRate.processingDate", date="2024-01-15T00:00:00+00:00"
    )
    plan = deep_fetch.plan("DepositRate", op, RATE)
    assert plan.root_operation == And(
        operands=(
            # business defaults to latest (never pinned by this operation)
            Comparison(op="eq", attr="Rate.businessTo", value="infinity"),
            # processing is pinned to the past instant (containment)
            Comparison(
                op="lessThanEquals", attr="Rate.processingFrom", value="2024-01-15T00:00:00+00:00"
            ),
            Comparison(
                op="greaterThan", attr="Rate.processingTo", value="2024-01-15T00:00:00+00:00"
            ),
        )
    )
