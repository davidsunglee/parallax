"""Relationship-navigation canonicalization unit tests (m-navigate).

Exercises `parallax.core.navigate.canonicalize_validated` independently of the
Docker-gated compile/run sweeps: per-hop as-of propagation (declared-axis
matching, the latest default, a non-temporal hop carrying no term, a temporal
hop reached from a polymorphic position resolving through the family root),
multi-hop propagation of the SAME root pin, and the strict-identity rule for a
navigation-free predicate. The as-of assertions read the `where` clause the
validated planning path lowers each read to.
"""

from __future__ import annotations

import datetime as dt
import decimal

import pytest

from parallax.conformance import models
from parallax.core import predicate as oa
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityMetadata, Metamodel
from parallax.core.navigate import canonicalize_validated
from parallax.core.object_query import AsOf, TemporalSelection
from parallax.core.object_query import TemporalDimension as QueryTemporalDimension
from tests._support.sql import compile_read
from tests.unit._corpus_model_support import model as accepted_model
from tests.unit._corpus_model_support import target

ORDERS = accepted_model("orders")
POLICY = accepted_model("policy")
LEASE = accepted_model("lease")

_B = "2024-03-01T00:00:00Z"
_P = "2024-02-01T00:00:00Z"
_B_MANAGED = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_P_MANAGED = dt.datetime(2024, 2, 1, tzinfo=dt.UTC)

# A hop's bare `Class.relationship` reference resolves relative to the Entity the
# reference is written against, so every canonicalization names the read's own
# queried Entity alongside its model.
ORDER = target(ORDERS, "Order")
LEASE_ENTITY = target(LEASE, "Lease")


def _canonical(op: oa.PredicateNode, model: Metamodel, entity: EntityMetadata) -> oa.PredicateNode:
    """``op`` validated against ``entity`` and canonicalized, as authored."""
    return canonicalize_validated(oa.validate_predicate(entity, op, model), model, entity).authored


def _where(
    op: oa.PredicateNode,
    model: Metamodel,
    name: str,
    *,
    temporal: dict[QueryTemporalDimension, TemporalSelection] | None = None,
) -> tuple[str, tuple[object, ...]]:
    """The `where` clause and binds `m-sql` lowers ``op`` to over ``model``."""
    statement = compile_read(
        op,
        model,
        POSTGRES,
        target(model, name),
        temporal=temporal,
    ).statement
    _, _, where = statement.sql.partition(" where ")
    return where, statement.binds


# --------------------------------------------------------------------------- #
# Strict identity for navigation-free predicates.                             #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "op",
    [
        oa.Or(
            operands=(
                oa.Comparison(op="lessThan", attr="Order.qty", value=10),
                oa.Comparison(op="greaterThan", attr="Order.qty", value=25),
            )
        ),
        oa.All(),
    ],
    ids=["navigation-free", "unfiltered"],
)
def test_canonicalization_is_identity_without_any_navigation_node(op: oa.PredicateNode) -> None:
    product = oa.validate_predicate(ORDER, op, ORDERS)
    assert canonicalize_validated(product, ORDERS, ORDER) is product


def test_walk_recurses_through_predicate_combinators_only() -> None:
    hop = oa.Exists(rel="Order.items")
    wrapped_ops: list[oa.PredicateNode] = [
        oa.Or(operands=(hop, oa.All())),
        oa.Not(operand=hop),
        oa.Group(operand=hop),
        oa.Narrow(to=("Order",), operand=hop),
    ]
    for op in wrapped_ops:
        product = oa.validate_predicate(ORDER, op, ORDERS)
        canonical = canonicalize_validated(product, ORDERS, ORDER)
        assert canonical is not product
        assert type(canonical.authored) is type(op), op


def test_validated_walk_rebuilds_not_and_group_wrappers_around_navigation() -> None:
    for authored in (
        oa.Not(operand=oa.Exists(rel="Order.items")),
        oa.Group(operand=oa.Exists(rel="Order.items")),
    ):
        product = oa.validate_predicate(ORDER, authored, ORDERS)

        canonical = canonicalize_validated(product, ORDERS, ORDER, {})

        assert type(canonical.authored) is type(authored)


# --------------------------------------------------------------------------- #
# Non-temporal relationship target: no as-of term at all.                     #
# --------------------------------------------------------------------------- #
def test_non_temporal_target_carries_no_as_of_term() -> None:
    inner = oa.Comparison(op="eq", attr="OrderItem.sku", value="A-100")
    canonical = _canonical(oa.Exists(rel="Order.items", op=inner), ORDERS, ORDER)
    assert isinstance(canonical, oa.Exists)
    assert canonical.op == inner


def test_non_temporal_bare_hop_stays_op_none() -> None:
    canonical = _canonical(oa.Exists(rel="Order.items"), ORDERS, ORDER)
    assert isinstance(canonical, oa.Exists)
    assert canonical.op is None


# --------------------------------------------------------------------------- #
# The two mixed-temporality directions (m-navigate "As-of propagation across   #
# relationships"), pinned against the real `lease.yaml` corpus model, whose    #
# own header comment names exactly this pair: `Tenant.leases` is non-temporal  #
# -> temporal (the child defaults every axis to LATEST); `Lease.notes` is      #
# temporal -> non-temporal (the child carries NO as-of term).                  #
# --------------------------------------------------------------------------- #
def test_non_temporal_root_reaching_a_temporal_target_defaults_every_axis_to_latest() -> None:
    op = oa.Exists(rel="Tenant.leases")
    where, binds = _where(op, LEASE, "Tenant")
    assert where == "exists (select 1 from lease t1 where t1.tenant_id = t0.id and t1.out_z = ?)"
    assert binds == ("infinity",)


def test_temporal_root_reaching_a_non_temporal_target_carries_no_as_of_term() -> None:
    inner = oa.Comparison(op="eq", attr="LeaseNote.text", value="renewed")
    canonical = _canonical(oa.Exists(rel="Lease.notes", op=inner), LEASE, LEASE_ENTITY)
    assert isinstance(canonical, oa.Exists)
    assert canonical.op == inner


# --------------------------------------------------------------------------- #
# Temporal target: latest default (root_pins omitted/empty).                  #
# --------------------------------------------------------------------------- #
def test_bare_hop_over_a_temporal_target_gets_the_latest_default_both_axes() -> None:
    op = oa.Exists(
        rel="Policy.coverages",
        op=oa.Comparison(op="greaterThanEquals", attr="Coverage.amount", value="600.00"),
    )
    where, binds = _where(
        op,
        POLICY,
        "Policy",
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and t1.amount >= ? "
        "and t1.thru_z = ? and t1.out_z = ?) and t0.thru_z = ? and t0.out_z = ?"
    )
    assert binds == (decimal.Decimal("600.00"), "infinity", "infinity", "infinity", "infinity")


def test_bare_hop_with_no_inner_op_gets_only_the_as_of_term() -> None:
    op = oa.Exists(rel="Policy.coverages")
    where, binds = _where(
        op,
        POLICY,
        "Policy",
        temporal={"valid-time": AsOf("latest"), "transaction-time": AsOf("latest")},
    )
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id "
        "and t1.thru_z = ? and t1.out_z = ?) and t0.thru_z = ? and t0.out_z = ?"
    )
    assert binds == ("infinity", "infinity", "infinity", "infinity")


# --------------------------------------------------------------------------- #
# Temporal target: an explicit root pin propagates verbatim, matched by axis. #
# --------------------------------------------------------------------------- #
def test_root_pinned_instant_propagates_to_the_hop_valid_time_first() -> None:
    op = oa.Exists(rel="Policy.coverages")
    where, binds = _where(
        op,
        POLICY,
        "Policy",
        temporal={"valid-time": AsOf(_B), "transaction-time": AsOf(_P)},
    )
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?) "
        "and t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?"
    )
    assert binds == (
        _B_MANAGED,
        _B_MANAGED,
        _P_MANAGED,
        _P_MANAGED,
        _B_MANAGED,
        _B_MANAGED,
        _P_MANAGED,
        _P_MANAGED,
    )


def test_root_pin_on_one_axis_only_still_defaults_the_other_to_latest() -> None:
    op = oa.Exists(rel="Policy.coverages")
    where, binds = _where(
        op,
        POLICY,
        "Policy",
        temporal={"valid-time": AsOf(_B), "transaction-time": AsOf("latest")},
    )
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.out_z = ?) "
        "and t0.from_z <= ? and t0.thru_z > ? and t0.out_z = ?"
    )
    assert binds == (
        _B_MANAGED,
        _B_MANAGED,
        "infinity",
        _B_MANAGED,
        _B_MANAGED,
        "infinity",
    )


# --------------------------------------------------------------------------- #
# Multi-hop: the SAME root pin rides every hop, however deep.                  #
# --------------------------------------------------------------------------- #
def test_multi_hop_propagates_the_same_root_pin_to_every_hop() -> None:
    op = oa.Exists(rel="Policy.coverages", op=oa.Exists(rel="Coverage.claims"))
    where, binds = _where(
        op,
        POLICY,
        "Policy",
        temporal={"valid-time": AsOf(_B), "transaction-time": AsOf(_P)},
    )
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "exists (select 1 from claim t2 where t2.coverage_id = t1.id and "
        "t2.from_z <= ? and t2.thru_z > ? and t2.in_z <= ? and t2.out_z > ?) and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?) "
        "and t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?"
    )
    # The inner hop's as-of binds lower BEFORE the outer hop's own (source order).
    assert binds == (
        _B_MANAGED,
        _B_MANAGED,
        _P_MANAGED,
        _P_MANAGED,
        _B_MANAGED,
        _B_MANAGED,
        _P_MANAGED,
        _P_MANAGED,
        _B_MANAGED,
        _B_MANAGED,
        _P_MANAGED,
        _P_MANAGED,
    )


# --------------------------------------------------------------------------- #
# Polymorphic relationship target: the family ROOT declares the as-of axes,   #
# so canonicalization resolves through it even when the relationship names    #
# an abstract subtype or a concrete leaf (m-inheritance "temporal axes are    #
# declared on the family's abstract root and inherited by every concrete").   #
# No corpus model combines a polymorphic target with a temporal family, so    #
# this is a synthetic descriptor mirroring `rate.yaml` / `animal.yaml`.       #
# --------------------------------------------------------------------------- #
_ZOO_MODEL = {
    "entities": [
        {
            "name": "Zoo",
            "table": "zoo",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGeneration": "application-assigned",
                }
            ],
            "relationships": [
                {
                    "name": "creatures",
                    "cardinality": "one-to-many",
                    "join": {
                        "source": "id",
                        "target": {"entity": "Creature", "attribute": "zooId"},
                    },
                }
            ],
        },
        {
            "name": "Creature",
            "table": "lion",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "temporality": "bitemporal",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGeneration": "application-assigned",
                },
                {"name": "zooId", "type": "int64", "column": "zoo_id", "nullable": True},
            ],
        },
        {
            "name": "Lion",
            "inheritance": {"role": "concrete-subtype", "parent": "Creature", "tagValue": "lion"},
            "attributes": [{"name": "roar", "type": "boolean", "column": "roar", "nullable": True}],
        },
    ]
}
_ZOO = models.accepted_model(_ZOO_MODEL)


def test_polymorphic_temporal_relationship_target_resolves_axes_via_the_family_root() -> None:
    # `Zoo.creatures` targets the abstract root `Creature` directly, so this also
    # covers the non-narrowed, whole-family case (m-sql injects no tag predicate).
    op = oa.Exists(rel="Zoo.creatures")
    where, binds = _where(op, _ZOO, "Zoo")
    assert where == (
        "exists (select 1 from lion t1 where t1.zoo_id = t0.id and t1.thru_z = ? and t1.out_z = ?)"
    )
    assert binds == ("infinity", "infinity")
