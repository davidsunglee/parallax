"""Temporal resolution of relationship hops (m-navigate).

Exercises `parallax.core.navigate.resolve_temporal_visibility` independently of
the Docker-gated compile/run sweeps. The typed half asserts the perspective each
reached relationship carries across every predicate position, the root
treatment each resolution mode finishes with, and the static lifecycle the
closed product enforces. The SQL half reads the `where` clause the resolved
planning path lowers each read to: declared-axis matching, the latest default,
a non-temporal hop carrying no term, a temporal hop reached from a polymorphic
position resolving through the family root, and the SAME root pin on every hop.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import decimal
from typing import TYPE_CHECKING, Never, assert_type, cast

import pytest

from parallax.conformance import models
from parallax.core import predicate as oa
from parallax.core.base import INFINITY
from parallax.core.deep_fetch import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.dialect import POSTGRES
from parallax.core.metamodel import EntityIdentity, EntityMetadata, Metamodel
from parallax.core.navigate import (
    NoRootSelections,
    PropagatedRootSelections,
    RootSelections,
    TemporallyResolvedPredicate,
    TemporalResolution,
    resolve_temporal_visibility,
)
from parallax.core.object_query import AsOf, History, TemporalSelection, validate_object_query
from parallax.core.object_query import object_query as authored_query
from parallax.core.object_query._nodes import TemporalDimension as QueryTemporalDimension
from parallax.core.object_query._resolved import ResolvedObjectQuery
from parallax.core.predicate._perspective import (
    AtPerspective,
    LatestPerspective,
    TemporalPerspective,
)
from parallax.core.predicate._resolved import (
    RelatedObject,
    ResolvedAnd,
    ResolvedComparison,
    ResolvedConstant,
    ResolvedGroup,
    ResolvedMembership,
    ResolvedNarrow,
    ResolvedNot,
    ResolvedNullCheck,
    ResolvedOr,
    ResolvedPredicate,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRange,
    ResolvedRelationship,
    ResolvedStringMatch,
    SubjectPosition,
)
from parallax.core.sql_gen._compile import compile_write_predicate
from parallax.core.temporal_read import Bitemporal, TransactionTimeOnly
from parallax.core.temporal_read import view as temporal_view
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
# reference is written against, so every resolution names the read's own queried
# Entity alongside its model.
ORDER = target(ORDERS, "Order")


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


def _query(
    op: oa.PredicateNode,
    model: Metamodel,
    name: str,
    temporal: dict[QueryTemporalDimension, TemporalSelection] | None = None,
) -> ResolvedObjectQuery:
    entity = target(model, name)
    return validate_object_query(
        entity, authored_query(entity.identity, op, temporal=temporal), model
    )


def _relationships(predicate: ResolvedPredicate) -> list[ResolvedRelationship]:
    """Every relationship ``predicate`` reaches, in the order its nodes hold them."""
    match predicate:
        case ResolvedAnd(operands=operands) | ResolvedOr(operands=operands):
            return [found for operand in operands for found in _relationships(operand)]
        case ResolvedNot(operand=operand) | ResolvedGroup(operand=operand):
            return _relationships(operand)
        case (
            ResolvedComparison()
            | ResolvedRange()
            | ResolvedMembership()
            | ResolvedStringMatch()
            | ResolvedNullCheck()
        ):
            return _hops(predicate.position)
        case ResolvedQuantifier(collection=collection, where=where, position=position):
            reached = [collection] if isinstance(collection, ResolvedRelationship) else []
            return [*_hops(position), *reached, *_operand(where)]
        case ResolvedPresence(target=target_, where=where, position=position):
            reached = [target_] if isinstance(target_, ResolvedRelationship) else []
            return [*_hops(position), *reached, *_operand(where)]
        case ResolvedNarrow(operand=operand, target=position):
            return [*_hops(position), *_operand(operand)]
        case ResolvedConstant():
            return []


def _operand(predicate: ResolvedPredicate | None) -> list[ResolvedRelationship]:
    return [] if predicate is None else _relationships(predicate)


def _hops(position: SubjectPosition) -> list[ResolvedRelationship]:
    if isinstance(position, RelatedObject):
        return [*_hops(position.source), position.relationship]
    return []


def _bitemporal(model: Metamodel, name: str) -> Bitemporal:
    shape = temporal_view(model).shape(target(model, name).identity)
    assert isinstance(shape, Bitemporal)
    return shape


def _pinned(model: Metamodel, name: str) -> TemporalPerspective:
    shape = _bitemporal(model, name)
    return TemporalPerspective(
        valid_time=AtPerspective(shape.valid_time, _B_MANAGED),
        transaction_time=AtPerspective(shape.transaction_time, _P_MANAGED),
    )


def _latest(model: Metamodel, name: str) -> TemporalPerspective:
    shape = temporal_view(model).shape(target(model, name).identity)
    if isinstance(shape, TransactionTimeOnly):
        return TemporalPerspective(transaction_time=LatestPerspective(shape.transaction_time))
    assert isinstance(shape, Bitemporal)
    return TemporalPerspective(
        valid_time=LatestPerspective(shape.valid_time),
        transaction_time=LatestPerspective(shape.transaction_time),
    )


_PINNED: dict[QueryTemporalDimension, TemporalSelection] = {
    "valid-time": AsOf(_B),
    "transaction-time": AsOf(_P),
}


# --------------------------------------------------------------------------- #
# Every reached relationship carries its target's perspective.                #
# --------------------------------------------------------------------------- #
_AUTO = oa.Comparison(op="eq", subject=oa.FieldSubject("Claim.coverage.policy.name"), value="Auto")
_POSITIONS: list[tuple[str, oa.PredicateNode, tuple[str, ...]]] = [
    ("Claim", _AUTO, ("Coverage", "Policy")),
    (
        "Claim",
        oa.Range(subject=oa.FieldSubject("Claim.coverage.amount"), lower="1.00", upper="9.00"),
        ("Coverage",),
    ),
    (
        "Claim",
        oa.Membership(op="in", subject=oa.FieldSubject("Claim.coverage.amount"), values=("1.00",)),
        ("Coverage",),
    ),
    (
        "Claim",
        oa.StringMatch(
            op="startsWith", subject=oa.FieldSubject("Claim.coverage.policy.name"), value="A"
        ),
        ("Coverage", "Policy"),
    ),
    (
        "OrderItem",
        oa.NullCheck(op="isNull", subject=oa.FieldSubject("OrderItem.order.sku")),
        ("Order",),
    ),
    (
        "Policy",
        oa.Quantifier(
            "any",
            "Policy.coverages",
            oa.Quantifier(
                "all",
                "claims",
                oa.Comparison(op="greaterThan", subject=oa.FieldSubject("reserve"), value="1.00"),
            ),
        ),
        ("Coverage", "Claim"),
    ),
    ("Claim", oa.Quantifier("none", "Claim.coverage.claims"), ("Coverage", "Claim")),
    (
        "Claim",
        oa.Presence(
            "exists",
            "Claim.coverage",
            oa.Presence(
                "notExists",
                "policy",
                oa.Comparison(op="eq", subject=oa.FieldSubject("name"), value="Auto"),
            ),
        ),
        ("Coverage", "Policy"),
    ),
    ("Claim", oa.Presence("exists", "Claim.coverage.policy"), ("Coverage", "Policy")),
    (
        "Claim",
        oa.Narrow(
            path="Claim.coverage",
            to=("Coverage",),
            operand=oa.Comparison(op="eq", subject=oa.FieldSubject("policy.name"), value="Auto"),
        ),
        ("Coverage", "Policy"),
    ),
    (
        "Claim",
        oa.And(
            operands=(
                oa.Or(operands=(oa.Not(operand=_AUTO), oa.Group(operand=_AUTO))),
                oa.Comparison(op="eq", subject=oa.FieldSubject("Claim.reserve"), value="1.00"),
            )
        ),
        ("Coverage", "Policy", "Coverage", "Policy"),
    ),
]


@pytest.mark.parametrize(
    ("name", "op", "reached"),
    _POSITIONS,
    ids=[
        "comparison-chain",
        "range",
        "membership",
        "string-match",
        "null-check",
        "nested-quantifiers",
        "quantifier-past-a-hop",
        "match-operand",
        "presence-past-a-hop",
        "narrowed-target-operand",
        "boolean-wrappers",
    ],
)
def test_every_reached_relationship_carries_its_target_perspective(
    name: str, op: oa.PredicateNode, reached: tuple[str, ...]
) -> None:
    temporal_root = name != "OrderItem"
    model = POLICY if temporal_root else ORDERS
    query = _query(op, model, name, _PINNED if temporal_root else None)
    assert all(found.temporal_visibility is None for found in _relationships(query.predicate))

    closed = resolve_temporal_visibility(
        query.predicate,
        target=query.root,
        model=model,
        resolution=PropagatedRootSelections(query.temporal),
    )

    relationships = _relationships(closed.predicate)
    assert tuple(found.target.identity.name for found in relationships) == reached
    for found in relationships:
        assert found.temporal_visibility == (
            _pinned(model, found.target.identity.name) if temporal_root else TemporalPerspective()
        )


def test_each_target_shape_selects_its_own_perspective() -> None:
    op = oa.Quantifier("any", "Tenant.leases", oa.Quantifier("any", "notes"))
    query = _query(op, LEASE, "Tenant")

    closed = resolve_temporal_visibility(
        query.predicate, target=query.root, model=LEASE, resolution=RootSelections(query.temporal)
    )

    lease, note = _relationships(closed.predicate)
    assert lease.temporal_visibility == _latest(LEASE, "Lease")
    assert note.temporal_visibility == TemporalPerspective()


def test_a_scanned_root_axis_sees_every_hop_at_latest_on_it() -> None:
    query = _query(
        oa.Quantifier("any", "Policy.coverages"),
        POLICY,
        "Policy",
        {"valid-time": History(), "transaction-time": AsOf(_P)},
    )

    closed = resolve_temporal_visibility(
        query.predicate, target=query.root, model=POLICY, resolution=RootSelections(query.temporal)
    )

    (coverage,) = _relationships(closed.predicate)
    shape = _bitemporal(POLICY, "Coverage")
    assert coverage.temporal_visibility == TemporalPerspective(
        valid_time=LatestPerspective(shape.valid_time),
        transaction_time=AtPerspective(shape.transaction_time, _P_MANAGED),
    )


# --------------------------------------------------------------------------- #
# Unresolved absence versus resolved non-temporal visibility.                 #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "op",
    [
        oa.Or(
            operands=(
                oa.Comparison(op="lessThan", subject=oa.FieldSubject("Order.qty"), value=10),
                oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Order.qty"), value=25),
            )
        ),
        oa.TrueNode(),
    ],
    ids=["navigation-free", "unfiltered"],
)
@pytest.mark.parametrize(
    "resolution",
    [RootSelections(()), PropagatedRootSelections(()), NoRootSelections()],
    ids=["root", "propagated", "none"],
)
def test_a_navigation_free_predicate_is_retained_by_every_resolution(
    op: oa.PredicateNode, resolution: TemporalResolution
) -> None:
    product = oa.validate_predicate(ORDER, op, ORDERS)
    closed = resolve_temporal_visibility(product, target=ORDER, model=ORDERS, resolution=resolution)
    assert closed.predicate is product


def test_a_non_temporal_hop_is_resolved_to_a_perspective_without_axes() -> None:
    hop = oa.Quantifier("any", "Order.items")
    for op in (
        hop,
        oa.Or(operands=(hop, oa.TrueNode())),
        oa.Not(operand=hop),
        oa.Group(operand=hop),
        oa.Narrow(to=("Order",), operand=hop),
    ):
        product = oa.validate_predicate(ORDER, op, ORDERS)
        closed = resolve_temporal_visibility(
            product, target=ORDER, model=ORDERS, resolution=NoRootSelections()
        )
        assert closed.predicate is not product
        assert type(closed.predicate) is type(product)
        ((before,), (after,)) = _relationships(product), _relationships(closed.predicate)
        assert before.temporal_visibility is None
        assert after.temporal_visibility == TemporalPerspective()
        assert after == dataclasses.replace(before, temporal_visibility=TemporalPerspective())


# --------------------------------------------------------------------------- #
# Each resolution mode finishes its own root treatment.                       #
# --------------------------------------------------------------------------- #
def _root_terms(model: Metamodel, name: str) -> tuple[tuple[str, str], ...]:
    """The (operator, member) of each current-object comparison ``name``'s
    pinned root restriction appends, in canonical axis order."""
    shape = _bitemporal(model, name)
    return tuple(
        (op, attribute.name)
        for axis in (shape.valid_time, shape.transaction_time)
        for op, attribute in (
            ("lessThanEquals", axis.start_attribute),
            ("greaterThan", axis.end_attribute),
        )
    )


def test_root_selections_append_the_root_terms_after_resolving_the_hops() -> None:
    query = _query(oa.Quantifier("any", "Policy.coverages"), POLICY, "Policy", _PINNED)

    closed = resolve_temporal_visibility(
        query.predicate, target=query.root, model=POLICY, resolution=RootSelections(query.temporal)
    )

    assert isinstance(closed.predicate, ResolvedAnd)
    hop, *terms = closed.predicate.operands
    assert isinstance(hop, ResolvedQuantifier)
    assert isinstance(hop.collection, ResolvedRelationship)
    assert hop.collection.temporal_visibility == _pinned(POLICY, "Coverage")
    assert all(isinstance(term, ResolvedComparison) for term in terms)
    assert tuple(
        (term.op, term.member.identity.name)
        for term in terms
        if isinstance(term, ResolvedComparison)
    ) == _root_terms(POLICY, "Policy")


def test_propagated_root_selections_inject_the_targets_terms_after_resolving_the_hops() -> None:
    query = _query(oa.Quantifier("any", "Coverage.claims"), POLICY, "Coverage", _PINNED)

    closed = resolve_temporal_visibility(
        query.predicate,
        target=query.root,
        model=POLICY,
        resolution=PropagatedRootSelections(query.temporal),
    )

    assert isinstance(closed.predicate, ResolvedAnd)
    hop, *terms = closed.predicate.operands
    assert isinstance(hop, ResolvedQuantifier)
    assert _relationships(hop)[0].temporal_visibility == _pinned(POLICY, "Claim")
    assert tuple(
        (term.op, term.member.identity.name)
        for term in terms
        if isinstance(term, ResolvedComparison)
    ) == _root_terms(POLICY, "Coverage")


def _held(name: str, temporality: str, *relationships: dict[str, object]) -> dict[str, object]:
    """``name``, keyed by ``id``, held through ``ownerId`` by whatever holds it."""
    return {
        "name": name,
        "table": name.lower(),
        "temporality": temporality,
        "attributes": [
            {
                "name": "id",
                "type": "int64",
                "column": "id",
                "primaryKey": True,
                "pkGeneration": "application-assigned",
            },
            {"name": "ownerId", "type": "int64", "column": "owner_id", "nullable": True},
        ],
        "relationships": list(relationships),
    }


def _holds(name: str, held: str) -> dict[str, object]:
    return {
        "name": name,
        "cardinality": "one-to-many",
        "join": {"source": "id", "target": {"entity": held, "attribute": "ownerId"}},
    }


# A Bitemporal Desk holds a Transaction-Time-Only Ledger, which holds Bitemporal
# Rates: the selections a Desk propagates to a Ledger state no Valid Time.
_DESK = models.accepted_model(
    {
        "entities": [
            _held("Desk", "bitemporal", _holds("ledgers", "Ledger")),
            _held("Ledger", "transaction-time", _holds("rates", "Rate")),
            _held("Rate", "bitemporal"),
        ]
    }
)


def _transaction_time_terms(model: Metamodel, name: str) -> tuple[tuple[str, str], ...]:
    shape = temporal_view(model).shape(target(model, name).identity)
    assert isinstance(shape, TransactionTimeOnly)
    axis = shape.transaction_time
    return (
        ("lessThanEquals", axis.start_attribute.name),
        ("greaterThan", axis.end_attribute.name),
    )


def test_a_transaction_time_only_child_sees_a_bitemporal_hop_at_the_roots_valid_time() -> None:
    root = _query(oa.TrueNode(), _DESK, "Desk", _PINNED)
    ledger = target(_DESK, "Ledger")
    product = oa.validate_predicate(ledger, oa.Quantifier("any", "Ledger.rates"), _DESK)

    closed = resolve_temporal_visibility(
        product, target=ledger, model=_DESK, resolution=PropagatedRootSelections(root.temporal)
    )

    assert isinstance(closed.predicate, ResolvedAnd)
    hop, *terms = closed.predicate.operands
    assert isinstance(hop, ResolvedQuantifier)
    assert _relationships(hop)[0].temporal_visibility == _pinned(_DESK, "Rate")
    assert tuple(
        (term.op, term.member.identity.name)
        for term in terms
        if isinstance(term, ResolvedComparison)
    ) == _transaction_time_terms(_DESK, "Ledger")


def test_no_root_selections_add_nothing_but_still_resolve_each_hop_at_latest() -> None:
    claim = target(POLICY, "Claim")
    product = oa.validate_predicate(claim, _AUTO, POLICY)

    closed = resolve_temporal_visibility(
        product, target=claim, model=POLICY, resolution=NoRootSelections()
    )

    assert isinstance(closed.predicate, ResolvedComparison)
    assert [found.temporal_visibility for found in _relationships(closed.predicate)] == [
        _latest(POLICY, "Coverage"),
        _latest(POLICY, "Policy"),
    ]


# --------------------------------------------------------------------------- #
# The closed product is a static lifecycle boundary.                          #
# --------------------------------------------------------------------------- #
def test_the_closed_product_is_obtained_only_by_resolving() -> None:
    with pytest.raises(TypeError):
        TemporallyResolvedPredicate()  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        TemporallyResolvedPredicate(ResolvedConstant(True), None)  # pyright: ignore[reportCallIssue]
    with pytest.raises(TypeError):
        TemporallyResolvedPredicate(cast("Never", ResolvedConstant(True)))


if TYPE_CHECKING:

    def _static_lifecycle_probes(  # pyright: ignore[reportUnusedFunction] - static contract probe
        raw: ResolvedPredicate, entity: EntityMetadata, identity: EntityIdentity
    ) -> None:
        """Typechecked, never called: closure yields the only compiler input, and
        neither a raw predicate nor a closed one crosses the wrong seam."""
        closed = resolve_temporal_visibility(
            raw, target=entity, model=POLICY, resolution=NoRootSelections()
        )
        assert_type(closed, TemporallyResolvedPredicate)
        projection = ResolvedReadProjection((), False)
        assert_type(PlannedEntityQuery(identity, entity, closed, projection), PlannedEntityQuery)
        compile_write_predicate(closed, POLICY, POSTGRES, entity)

        PlannedEntityQuery(identity, entity, raw, projection)  # pyright: ignore[reportArgumentType]
        compile_write_predicate(raw, POLICY, POSTGRES, entity)  # pyright: ignore[reportArgumentType]
        resolve_temporal_visibility(
            closed,  # pyright: ignore[reportArgumentType]
            target=entity,
            model=POLICY,
            resolution=NoRootSelections(),
        )


# --------------------------------------------------------------------------- #
# The two mixed-temporality directions (m-navigate "As-of propagation across   #
# relationships"), pinned against the real `lease.yaml` corpus model, whose    #
# own header comment names exactly this pair: `Tenant.leases` is non-temporal  #
# -> temporal (the child defaults every axis to LATEST); `Lease.notes` is      #
# temporal -> non-temporal (the child carries NO as-of term).                  #
# --------------------------------------------------------------------------- #
def test_non_temporal_root_reaching_a_temporal_target_defaults_every_axis_to_latest() -> None:
    op = oa.Quantifier("any", "Tenant.leases")
    where, binds = _where(op, LEASE, "Tenant")
    assert where == "exists (select 1 from lease t1 where t1.tenant_id = t0.id and t1.out_z = ?)"
    assert binds == (INFINITY,)


# --------------------------------------------------------------------------- #
# Temporal target: latest default (root_pins omitted/empty).                  #
# --------------------------------------------------------------------------- #
def test_bare_hop_over_a_temporal_target_gets_the_latest_default_both_axes() -> None:
    op = oa.Quantifier(
        "any",
        "Policy.coverages",
        oa.Comparison(op="greaterThanEquals", subject=oa.FieldSubject("amount"), value="600.00"),
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
    assert binds == (decimal.Decimal("600.00"), INFINITY, INFINITY, INFINITY, INFINITY)


def test_bare_hop_with_no_inner_op_gets_only_the_as_of_term() -> None:
    op = oa.Quantifier("any", "Policy.coverages")
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
    assert binds == (INFINITY, INFINITY, INFINITY, INFINITY)


# --------------------------------------------------------------------------- #
# Temporal target: an explicit root pin propagates verbatim, matched by axis. #
# --------------------------------------------------------------------------- #
def test_root_pinned_instant_propagates_to_the_hop_valid_time_first() -> None:
    op = oa.Quantifier("any", "Policy.coverages")
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
    op = oa.Quantifier("any", "Policy.coverages")
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
        INFINITY,
        _B_MANAGED,
        _B_MANAGED,
        INFINITY,
    )


# --------------------------------------------------------------------------- #
# Multi-hop: the SAME root pin rides every hop, however deep.                  #
# --------------------------------------------------------------------------- #
def test_multi_hop_propagates_the_same_root_pin_to_every_hop() -> None:
    op = oa.Quantifier("any", "Policy.coverages", oa.Quantifier("any", "claims"))
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
# so propagation resolves through it even when the relationship names        #
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
    op = oa.Quantifier("any", "Zoo.creatures")
    where, binds = _where(op, _ZOO, "Zoo")
    assert where == (
        "exists (select 1 from lion t1 where t1.zoo_id = t0.id and t1.thru_z = ? and t1.out_z = ?)"
    )
    assert binds == (INFINITY, INFINITY)


# --------------------------------------------------------------------------- #
# To-one hops: the reached candidate is filtered by the same visibility.      #
# --------------------------------------------------------------------------- #
_COVERAGE_VISIBLE = "t1.from_z <= ? and t1.thru_z > ? and t1.in_z <= ? and t1.out_z > ?"
_CLAIM_VISIBLE = "t0.from_z <= ? and t0.thru_z > ? and t0.in_z <= ? and t0.out_z > ?"


def test_a_field_past_a_to_one_hop_reads_only_its_visible_candidate() -> None:
    op = oa.Comparison(
        op="greaterThan", subject=oa.FieldSubject("Claim.coverage.amount"), value="1.00"
    )
    statement = compile_read(
        op, POLICY, POSTGRES, target(POLICY, "Claim"), temporal=_PINNED
    ).statement
    assert statement.sql.endswith(
        f"from claim t0 left join coverage t1 on t1.id = t0.coverage_id and {_COVERAGE_VISIBLE} "
        f"where t1.amount > ? and {_CLAIM_VISIBLE}"
    )
    assert statement.binds[:4] == (_B_MANAGED, _B_MANAGED, _P_MANAGED, _P_MANAGED)
    assert statement.binds[4] == decimal.Decimal("1.00")


def test_presence_of_a_to_one_target_tests_only_its_visible_candidate() -> None:
    where, _ = _where(oa.Presence("notExists", "Claim.coverage"), POLICY, "Claim", temporal=_PINNED)
    assert where == (
        f"not exists (select 1 from coverage t1 where t1.id = t0.coverage_id and "
        f"{_COVERAGE_VISIBLE}) and {_CLAIM_VISIBLE}"
    )


def test_a_match_and_every_hop_its_operand_reaches_carry_their_terms() -> None:
    op = oa.Presence(
        "exists",
        "Claim.coverage",
        oa.Presence(
            "exists",
            "policy",
            oa.Comparison(op="eq", subject=oa.FieldSubject("name"), value="Auto"),
        ),
    )
    where, binds = _where(op, POLICY, "Claim", temporal=_PINNED)
    policy_visible = "t2.from_z <= ? and t2.thru_z > ? and t2.in_z <= ? and t2.out_z > ?"
    assert where == (
        "exists (select 1 from coverage t1 where t1.id = t0.coverage_id and exists "
        f"(select 1 from policy t2 where t2.id = t1.policy_id and t2.name = ? and "
        f"{policy_visible}) and {_COVERAGE_VISIBLE}) and {_CLAIM_VISIBLE}"
    )
    assert binds[0] == "Auto"
    assert binds[1:5] == (_B_MANAGED, _B_MANAGED, _P_MANAGED, _P_MANAGED)
