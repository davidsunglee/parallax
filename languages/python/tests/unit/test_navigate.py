"""Relationship-navigation canonicalization unit tests (m-navigate).

Exercises `parallax.core.navigate.canonicalize` independently of the Docker-gated
compile/run sweeps: per-hop as-of propagation (declared-axis matching, the
latest default, a non-temporal hop carrying no term, a temporal hop reached from
a polymorphic position resolving through the family root), multi-hop
propagation of the SAME root pin, and the strict-identity rule for a
navigation-free operation. Correlation-column / polymorphic-tag SQL emission is
`m-sql`'s own concern, covered in `test_sql_gen_navigation.py`; these tests feed
the rewritten operation straight to `compile_read` only to assert the FRAGMENT
`canonicalize` injected, never the join columns.
"""

from __future__ import annotations

import pytest

from parallax.conformance import models
from parallax.core import op_algebra as oa
from parallax.core.descriptor import deserialize
from parallax.core.dialect import POSTGRES
from parallax.core.navigate import canonicalize
from parallax.core.sql_gen import compile_read

pytestmark = pytest.mark.unit

_MODELS = models.load_models()
ORDERS = _MODELS["orders"]
POLICY = _MODELS["policy"]
LEASE = _MODELS["lease"]

_B = "2024-03-01T00:00:00+00:00"
_P = "2024-02-01T00:00:00+00:00"


def _where(op: oa.Operation, meta: object, target: str) -> tuple[str, tuple[object, ...]]:
    statement = compile_read(op, meta, POSTGRES, target).statement  # type: ignore[arg-type]
    _, _, where = statement.sql.partition(" where ")
    return where, statement.binds


# --------------------------------------------------------------------------- #
# Strict identity for navigation-free operations.                             #
# --------------------------------------------------------------------------- #
def test_canonicalize_is_identity_without_any_navigation_node() -> None:
    op = oa.Or(
        operands=(
            oa.Comparison(op="lessThan", attr="Order.qty", value=10),
            oa.Comparison(op="greaterThan", attr="Order.qty", value=25),
        )
    )
    assert canonicalize(op, ORDERS) is op


def test_canonicalize_is_identity_for_a_deep_fetch_root_with_no_navigation() -> None:
    op = oa.DeepFetch(operand=oa.All(), paths=((oa.PathSegment(rel="Order.items"),),))
    assert canonicalize(op, ORDERS) is op


def test_walk_recurses_through_every_wrapping_node_kind() -> None:
    """Robustness/coverage: `_walk` must recurse into every node kind that could
    nest a navigation hop, however unusual the composition — a directive or a
    temporal wrapper nested around a hop is not a shape `inject_as_of`'s own
    peeling would ever hand canonicalize (both are always peeled to the
    outermost position first), but a stray one must still be walked correctly
    rather than silently skipping the hop's own rewrite.
    """
    hop = oa.Exists(rel="Order.items")
    wrapped_ops: list[oa.Operation] = [
        oa.Or(operands=(hop, oa.All())),
        oa.Not(operand=hop),
        oa.Group(operand=hop),
        oa.OrderBy(operand=hop, keys=(oa.OrderKey(attr="Order.id"),)),
        oa.Limit(operand=hop, count=5),
        oa.Distinct(operand=hop),
        oa.AsOf(operand=hop, as_of_attr="Order.mystery", date="now"),
        oa.AsOfRange(
            operand=hop,
            as_of_attr="Order.mystery",
            from_="2024-01-01T00:00:00+00:00",
            to="2024-02-01T00:00:00+00:00",
        ),
        oa.History(operand=hop, as_of_attr="Order.mystery"),
        oa.DeepFetch(operand=hop, paths=()),
    ]
    for op in wrapped_ops:
        canonical = canonicalize(op, ORDERS)
        assert type(canonical) is type(op), op


# --------------------------------------------------------------------------- #
# Non-temporal relationship target: no as-of term at all.                     #
# --------------------------------------------------------------------------- #
def test_non_temporal_target_carries_no_as_of_term() -> None:
    inner = oa.Comparison(op="eq", attr="OrderItem.sku", value="A-100")
    op = oa.Exists(rel="Order.items", op=inner)
    canonical = canonicalize(op, ORDERS)
    assert isinstance(canonical, oa.Exists)
    assert canonical.op is inner


def test_non_temporal_bare_hop_stays_op_none() -> None:
    op = oa.Exists(rel="Order.items")
    canonical = canonicalize(op, ORDERS)
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
    canonical = canonicalize(oa.Exists(rel="Tenant.leases"), LEASE)
    where, binds = _where(canonical, LEASE, "Tenant")
    assert where == "exists (select 1 from lease t1 where t1.tenant_id = t0.id and t1.out_z = ?)"
    assert binds == ("infinity",)


def test_temporal_root_reaching_a_non_temporal_target_carries_no_as_of_term() -> None:
    inner = oa.Comparison(op="eq", attr="LeaseNote.text", value="renewed")
    canonical = canonicalize(oa.Exists(rel="Lease.notes", op=inner), LEASE)
    assert isinstance(canonical, oa.Exists)
    assert canonical.op is inner


# --------------------------------------------------------------------------- #
# Temporal target: latest default (root_pins omitted/empty).                  #
# --------------------------------------------------------------------------- #
def test_bare_hop_over_a_temporal_target_gets_the_latest_default_both_axes() -> None:
    op = oa.Exists(
        rel="Policy.coverages",
        op=oa.Comparison(op="greaterThanEquals", attr="Coverage.amount", value=600),
    )
    canonical = canonicalize(op, POLICY)
    where, binds = _where(canonical, POLICY, "Policy")
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and t1.amount >= ? "
        "and t1.thru_z = ? and t1.out_z = ?)"
    )
    assert binds == (600, "infinity", "infinity")


def test_bare_hop_with_no_inner_op_gets_only_the_as_of_term() -> None:
    canonical = canonicalize(oa.Exists(rel="Policy.coverages"), POLICY)
    where, binds = _where(canonical, POLICY, "Policy")
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id "
        "and t1.thru_z = ? and t1.out_z = ?)"
    )
    assert binds == ("infinity", "infinity")


# --------------------------------------------------------------------------- #
# Temporal target: an explicit root pin propagates verbatim, matched by axis. #
# --------------------------------------------------------------------------- #
def test_root_pinned_instant_propagates_to_the_hop_business_axis_first() -> None:
    op = oa.Exists(rel="Policy.coverages")
    canonical = canonicalize(op, POLICY, root_pins={"business": _B, "processing": _P})
    where, binds = _where(canonical, POLICY, "Policy")
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?)"
    )
    assert binds == (_B, _B, _P, _P)


def test_root_pin_on_one_axis_only_still_defaults_the_other_to_latest() -> None:
    op = oa.Exists(rel="Policy.coverages")
    canonical = canonicalize(op, POLICY, root_pins={"business": _B})
    where, binds = _where(canonical, POLICY, "Policy")
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.out_z = ?)"
    )
    assert binds == (_B, _B, "infinity")


# --------------------------------------------------------------------------- #
# Multi-hop: the SAME root pin rides every hop, however deep.                  #
# --------------------------------------------------------------------------- #
def test_multi_hop_propagates_the_same_root_pin_to_every_hop() -> None:
    op = oa.Exists(rel="Policy.coverages", op=oa.Exists(rel="Coverage.claims"))
    canonical = canonicalize(op, POLICY, root_pins={"business": _B, "processing": _P})
    where, binds = _where(canonical, POLICY, "Policy")
    assert where == (
        "exists (select 1 from coverage t1 where t1.policy_id = t0.id and "
        "exists (select 1 from claim t2 where t2.coverage_id = t1.id and "
        "t2.from_z <= ? and t2.thru_z > ? and t2.in_z <= ? and t2.out_z > ?) and "
        "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?)"
    )
    # The inner hop's as-of binds lower BEFORE the outer hop's own (source order).
    assert binds == (_B, _B, _P, _P, _B, _B, _P, _P)


# --------------------------------------------------------------------------- #
# Polymorphic relationship target: the family ROOT declares the as-of axes,   #
# so `canonicalize` must resolve through it even when the relationship names  #
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
            "mutability": "transactional",
            "temporal": "non-temporal",
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGenerator": "none",
                }
            ],
            "relationships": [
                {
                    "name": "creatures",
                    "relatedEntity": "Creature",
                    "cardinality": "one-to-many",
                    "join": "this.id = Creature.zooId",
                    "foreignKey": "zoo_id",
                }
            ],
        },
        {
            "name": "Creature",
            "mutability": "transactional",
            "temporal": "bitemporal",
            "inheritance": {
                "role": "root",
                "strategy": "table-per-hierarchy",
                "tag": {"column": "kind"},
            },
            "attributes": [
                {
                    "name": "id",
                    "type": "int64",
                    "column": "id",
                    "primaryKey": True,
                    "pkGenerator": "none",
                },
                {"name": "zooId", "type": "int64", "column": "zoo_id", "nullable": True},
                {"name": "businessFrom", "type": "timestamp", "column": "from_z"},
                {"name": "businessTo", "type": "timestamp", "column": "thru_z"},
                {"name": "processingFrom", "type": "timestamp", "column": "in_z"},
                {"name": "processingTo", "type": "timestamp", "column": "out_z"},
            ],
            "asOfAttributes": [
                {
                    "name": "businessDate",
                    "fromColumn": "from_z",
                    "toColumn": "thru_z",
                    "axis": "business",
                    "toIsInclusive": False,
                    "infinity": "infinity",
                    "default": "now",
                },
                {
                    "name": "processingDate",
                    "fromColumn": "in_z",
                    "toColumn": "out_z",
                    "axis": "processing",
                    "toIsInclusive": False,
                    "infinity": "infinity",
                    "default": "now",
                },
            ],
        },
        {
            "name": "Lion",
            "table": "lion",
            "mutability": "transactional",
            "inheritance": {"role": "concrete-subtype", "parent": "Creature", "tagValue": "lion"},
            "attributes": [{"name": "roar", "type": "boolean", "column": "roar", "nullable": True}],
        },
    ]
}
_ZOO = deserialize(_ZOO_MODEL)


def test_polymorphic_temporal_relationship_target_resolves_axes_via_the_family_root() -> None:
    # `Zoo.creatures` targets the abstract root `Creature` directly, so this also
    # covers the non-narrowed, whole-family case (m-sql injects no tag predicate).
    canonical = canonicalize(oa.Exists(rel="Zoo.creatures"), _ZOO)
    where, binds = _where(canonical, _ZOO, "Zoo")
    assert where == (
        "exists (select 1 from lion t1 where t1.zoo_id = t0.id and t1.thru_z = ? and t1.out_z = ?)"
    )
    assert binds == ("infinity", "infinity")
