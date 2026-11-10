"""Statement planning decisions, read without rendering SQL."""

from __future__ import annotations

import dataclasses
import datetime as dt

import pytest

from parallax.conformance.models import accepted_model
from parallax.core import inheritance, storage_layout
from parallax.core import predicate as oa
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.navigate import _closed  # pyright: ignore[reportPrivateUsage]
from parallax.core.object_query._resolved import ResolvedOrderTerm
from parallax.core.predicate._perspective import (
    AtPerspective,
    LatestPerspective,
    TemporalPerspective,
)
from parallax.core.predicate._resolved import (
    ResolvedAnd,
    ResolvedPresence,
    ResolvedQuantifier,
    ResolvedRelationship,
)
from parallax.core.read_planning import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.sql_gen._inheritance import (
    SingleTableReadPlan,
    plan_read_shape,
)
from parallax.core.sql_gen._planning import (
    REACHED_ROW,
    BranchSelection,
    CandidateExistence,
    Continuation,
    EvaluationContext,
    LexicalScopePlan,
    OwnerResultEvaluation,
    OwnerResultsRef,
    SharedRowEvaluation,
    SharedSourceRef,
    StatementPlan,
    TargetSelection,
    UnsharedEvaluation,
    plan_relationship_candidates,
    plan_statement,
    shared_relationship_is_eligible,
)
from parallax.core.temporal_read import Bitemporal, temporal_facet_of
from tests._support.sql import (
    read_position,
    resolved_as_stated,
)
from tests.unit._corpus_model_support import model, target
from tests.unit.core.sql_gen._badge_model_support import badge_model, temporal_badge_model
from tests.unit.core.sql_gen._plan_reuse_support import (
    ReadShape,
)

ORDERS = model("orders")
DOCUMENT = model("document")
POLICY = model("policy")
COLLECTIONS = model("predicate-collections")
TRAVERSAL = model("predicate-traversal")
DOCUMENT_LAYOUT = model("document-layout")


def _to_many(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    resolved = oa.validate_predicate(target(model, source), oa.Quantifier("any", path), model)
    assert isinstance(resolved, ResolvedQuantifier)
    assert isinstance(resolved.collection, ResolvedRelationship)
    return resolved.collection


def _to_one(model: Metamodel, source: str, path: str) -> ResolvedRelationship:
    resolved = oa.validate_predicate(target(model, source), oa.Presence("exists", path), model)
    assert isinstance(resolved, ResolvedPresence)
    assert isinstance(resolved.target, ResolvedRelationship)
    return resolved.target


def _eligible(model: Metamodel, hop: ResolvedRelationship, visibility: TemporalPerspective) -> bool:
    facet, storage = (
        inheritance.inheritance_facet_of(model),
        storage_layout.storage_layout_facet_of(model),
    )
    seen = dataclasses.replace(hop, temporal_visibility=visibility)
    candidates = plan_relationship_candidates(
        seen, position=None, meta=model, facet=facet, storage=storage
    )
    return shared_relationship_is_eligible(seen, candidates, facet=facet, storage=storage)


_INSTANT = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _seen(model: Metamodel, name: str, *, valid: bool, tx: bool) -> TemporalPerspective:
    """``name``'s visibility: Latest on each axis flagged, else At one instant."""
    shape = temporal_facet_of(model).shape(target(model, name).identity)
    assert isinstance(shape, Bitemporal)
    return TemporalPerspective(
        valid_time=(
            LatestPerspective(shape.valid_time)
            if valid
            else AtPerspective(shape.valid_time, _INSTANT)
        ),
        transaction_time=(
            LatestPerspective(shape.transaction_time)
            if tx
            else AtPerspective(shape.transaction_time, _INSTANT)
        ),
    )


def test_a_physical_unique_key_the_correlation_fixes_proves_a_non_temporal_hop() -> None:
    hop = _to_one(ORDERS, "OrderItem", "OrderItem.order")
    assert _eligible(ORDERS, hop, TemporalPerspective())


@pytest.mark.parametrize("unique", [True, False])
def test_a_nullable_correlated_column_is_proven_only_by_a_unique_key(unique: bool) -> None:
    family = badge_model(unique=unique)
    hop = _to_one(family, "Holder", "Holder.badge")
    assert _eligible(family, hop, TemporalPerspective()) is unique


@pytest.mark.parametrize(
    ("valid", "tx"),
    [(True, True), (False, True), (True, False), (False, False)],
    ids=["latest-latest", "at-latest", "latest-at", "at-at"],
)
def test_a_temporal_hop_correlated_by_its_logical_key_is_proven_at_any_perspective(
    valid: bool, tx: bool
) -> None:
    # Latest ends complete the physical key; an instant fixes no end, so the
    # logical key and the perspective's one milestone per axis prove it instead.
    hop = _to_one(POLICY, "Claim", "Claim.coverage")
    assert _eligible(POLICY, hop, _seen(POLICY, "Coverage", valid=valid, tx=tx))


@pytest.mark.parametrize(
    ("valid", "tx"),
    [(True, True), (False, True), (True, False), (False, False)],
    ids=["latest-latest", "at-latest", "latest-at", "at-at"],
)
def test_a_temporal_hop_off_its_logical_key_is_proven_by_a_unique_key_only_at_latest(
    valid: bool, tx: bool
) -> None:
    # The authored unique key ends with every axis end, and only a Latest axis
    # fixes its end; an instant on either axis leaves the key's end unfixed.
    for unique in (True, False):
        family = temporal_badge_model(unique=unique)
        hop = _to_one(family, "Holder", "Holder.badge")
        visibility = _seen(family, "Badge", valid=valid, tx=tx)
        assert _eligible(family, hop, visibility) is (unique and valid and tx)


def test_several_physical_candidates_are_never_proven_unique() -> None:
    hop = _to_many(DOCUMENT, "Folder", "Folder.documents")
    facet, storage = (
        inheritance.inheritance_facet_of(DOCUMENT),
        storage_layout.storage_layout_facet_of(DOCUMENT),
    )
    candidates = plan_relationship_candidates(
        hop, position=None, meta=DOCUMENT, facet=facet, storage=storage
    )
    assert len(candidates.branches) > 1
    assert not _eligible(DOCUMENT, hop, TemporalPerspective())


# --------------------------------------------------------------------------- #
# Statement plans                                                              #
# --------------------------------------------------------------------------- #


def _eq(path: str, value: oa.ScalarLiteral = "x") -> oa.Comparison:
    return oa.Comparison(op="eq", subject=oa.FieldSubject(path), value=value)


def _planned(
    family: Metamodel,
    root: str,
    node: oa.PredicateNode,
    *,
    context: EvaluationContext = EvaluationContext.SHARING_ALLOWED,
    narrow_to: tuple[str, ...] | None = None,
    order_by: tuple[str, ...] = (),
) -> StatementPlan:
    plan, _shape = _planned_shape(
        family, root, node, context=context, narrow_to=narrow_to, order_by=order_by
    )
    return plan


def _planned_shape(
    family: Metamodel,
    root: str,
    node: oa.PredicateNode,
    *,
    context: EvaluationContext = EvaluationContext.SHARING_ALLOWED,
    narrow_to: tuple[str, ...] | None = None,
    order_by: tuple[str, ...] = (),
) -> tuple[StatementPlan, ReadShape]:
    """``root``'s statement plan and the physical read plan it was planned over."""
    entity = target(family, root)
    facet, storage = (
        inheritance.inheritance_facet_of(family),
        storage_layout.storage_layout_facet_of(family),
    )
    narrowed = (
        None if narrow_to is None else tuple(target(family, name).identity for name in narrow_to)
    )
    predicate = resolved_as_stated(oa.validate_predicate(entity, node, family), family, entity)
    read = plan_read_shape(
        PlannedEntityQuery(
            target=entity.identity,
            entity=entity,
            position=read_position(family, entity, narrowed),
            predicate=predicate,
            projection=ResolvedReadProjection((), False),
            narrow_to=narrowed,
        ),
        facet,
        storage,
        False,
        False,
    )
    plan = plan_statement(
        predicate,
        evaluation_context=context,
        entity=entity,
        meta=family,
        facet=facet,
        storage=storage,
        read_shape=read,
        order_terms=tuple(_order_term(family, name) for name in order_by),
    )
    return plan, read


def _order_term(family: Metamodel, reference: str) -> ResolvedOrderTerm:
    owner, _, name = reference.rpartition(".")
    view = inheritance.inheritance_facet_of(family).entity(target(family, owner).identity)
    assert view is not None
    attribute = view.applicable_attribute(name)
    assert attribute is not None
    return ResolvedOrderTerm(attribute, "asc", "last")


def _root(plan: StatementPlan, concrete: EntityIdentity | None = None) -> LexicalScopePlan:
    return plan.lexical_scopes[plan.root_scopes[concrete]]


def _scope(plan: StatementPlan, scope_id: int | None) -> LexicalScopePlan:
    assert scope_id is not None
    return plan.lexical_scopes[scope_id]


_AT_ROW = UnsharedEvaluation(Continuation((), (REACHED_ROW,)))
_TAGGED_N = oa.StringMatch(op="startsWith", subject=oa.CURRENT_SCALAR_ELEMENT, value="n")


@pytest.mark.parametrize("identical", [True, False], ids=["same-object", "equal-valued"])
def test_each_quantifier_occurrence_reads_its_own_owner_result_cell(identical: bool) -> None:
    family = COLLECTIONS
    basket = target(family, "Basket")
    authored = oa.Quantifier("any", "Basket.owner.tags", _TAGGED_N)
    if identical:
        quantifier = resolved_as_stated(
            oa.validate_predicate(basket, authored, family), family, basket
        ).predicate
        predicate = _closed(ResolvedAnd((quantifier, quantifier)))
    else:
        predicate = resolved_as_stated(
            oa.validate_predicate(basket, oa.And(operands=(authored, authored)), family),
            family,
            basket,
        )
    plan = plan_statement(
        predicate,
        evaluation_context=EvaluationContext.SHARING_ALLOWED,
        entity=basket,
        meta=family,
        facet=inheritance.inheritance_facet_of(family),
        storage=storage_layout.storage_layout_facet_of(family),
    )
    root = _root(plan)
    results = OwnerResultsRef(root.scope_id, 0)
    assert root.placements == {
        (0,): OwnerResultEvaluation(results, 0),
        (1,): OwnerResultEvaluation(results, 1),
    }
    (owner_results,) = root.owner_results
    assert owner_results.owner == SharedSourceRef(root.scope_id, 0)
    assert [cell.path for cell in owner_results.cells] == [(0,), (1,)]
    first, second = (_scope(plan, cell.scope_id) for cell in owner_results.cells)
    assert first.scope_id != second.scope_id
    for cell in (first, second):
        assert cell.predicate == root.predicate.operands[0]  # type: ignore[union-attr]
        assert cell.placements == {(): _AT_ROW, (0,): _AT_ROW}
        assert cell.sources == cell.owner_results == ()


def test_a_candidate_operand_shares_only_where_its_context_allows() -> None:
    op = oa.Quantifier("any", "Owner.baskets", _eq("owner.manager.name"))
    for context, shared in (
        (EvaluationContext.SHARING_ALLOWED, True),
        (EvaluationContext.SHARING_FORBIDDEN, False),
    ):
        plan = _planned(COLLECTIONS, "Owner", op, context=context)
        root = _root(plan)
        assert root.sources == ()
        placement = root.placements[()]
        assert isinstance(placement, UnsharedEvaluation)
        (existence,) = placement.continuation.terminals
        assert isinstance(existence, CandidateExistence)
        (candidate,) = existence.candidates
        operand = _scope(plan, candidate.operand_scope)
        evaluated = operand.placements[()]
        if shared:
            assert len(operand.sources) == 2
            assert isinstance(evaluated, SharedRowEvaluation)
        else:
            assert operand.sources == ()
            assert isinstance(evaluated, UnsharedEvaluation)
            assert [hop.relationship.identity.name for hop in evaluated.continuation.hops] == [
                "owner",
                "manager",
            ]


def test_a_hop_in_forbidden_context_keeps_every_candidate_unshared() -> None:
    plan = _planned(
        TRAVERSAL,
        "Ticket",
        _eq("Ticket.parking.vehicle.maker"),
        context=EvaluationContext.SHARING_FORBIDDEN,
    )
    root = _root(plan)
    assert root.sources == ()
    placement = root.placements[()]
    assert isinstance(placement, UnsharedEvaluation)
    assert [len(hop.candidates.branches) for hop in placement.continuation.hops] == [1, 2]


def test_a_narrowed_target_decides_each_candidate_branch() -> None:
    seats = oa.Comparison(op="greaterThan", subject=oa.FieldSubject("seats"), value=2)
    plan = _planned(
        TRAVERSAL, "Parking", oa.Narrow(path="Parking.vehicle", to=("Car",), operand=seats)
    )
    placement = _root(plan).placements[()]
    assert isinstance(placement, UnsharedEvaluation)
    (hop,) = placement.continuation.hops
    assert [branch.table for branch in hop.candidates.branches] == [
        "traversal_bike",
        "traversal_car",
    ]
    bike, car = placement.continuation.terminals
    assert bike == TargetSelection(False, None)
    assert isinstance(car, TargetSelection)
    assert car.selection is True
    assert _scope(plan, car.operand_scope).placements == {(): _AT_ROW}


def test_a_narrowed_existence_selects_its_branches_but_a_universal_keeps_every_one() -> None:
    invoices = oa.Narrow(to=("Invoice",), operand=oa.TrueNode())
    counts: dict[str, int] = {}
    for kind in ("any", "all"):
        plan = _planned(DOCUMENT, "Folder", oa.Quantifier(kind, "Folder.documents", invoices))
        placement = _root(plan).placements[()]
        assert isinstance(placement, UnsharedEvaluation)
        (existence,) = placement.continuation.terminals
        assert isinstance(existence, CandidateExistence)
        counts[kind] = len(existence.candidates)
        if kind == "all":
            selections = [
                _scope(plan, candidate.operand_scope).placements[()]
                for candidate in existence.candidates
            ]
            assert {
                selection.continuation.terminals[0]
                for selection in selections
                if isinstance(selection, UnsharedEvaluation)
            } == {BranchSelection(True), BranchSelection(False)}
    assert counts["any"] == 1
    assert counts["all"] > 1


def _concretes(family: Metamodel, *names: str) -> list[EntityIdentity]:
    return [target(family, name).identity for name in names]


_CARD_OR_CASH = oa.Or(
    operands=(
        oa.Narrow(to=("CardPayment",), operand=_eq("CardPayment.detail", "visa-4242")),
        oa.Narrow(
            to=("CashPayment",),
            operand=oa.Comparison(
                op="greaterThan", subject=oa.FieldSubject("CashPayment.detail"), value="10.00"
            ),
        ),
    )
)


def test_a_partitioning_tph_read_plans_one_root_per_concrete_before_rendering() -> None:
    # The untouched abstract root carries no outer tag guard, and still
    # partitions: the guard's absence does not decide the strategy.
    plan, shape = _planned_shape(DOCUMENT_LAYOUT, "Payment", _CARD_OR_CASH)
    assert isinstance(shape, SingleTableReadPlan)
    assert shape.tag_guard is None
    assert plan.requires_tph_partition
    card, cash = _concretes(DOCUMENT_LAYOUT, "CardPayment", "CashPayment")
    assert list(plan.root_scopes) == [card, cash]
    for concrete, selected in ((card, (True, False)), (cash, (False, True))):
        root = _root(plan, concrete)
        terminals = tuple(
            placement.continuation.terminals[0]
            for path in ((0,), (1,))
            if isinstance(placement := root.placements[path], UnsharedEvaluation)
        )
        assert terminals == tuple(BranchSelection(flag) for flag in selected)
        assert ((0, 0) in root.placements, (1, 0) in root.placements) == selected


@pytest.mark.parametrize(
    ("node", "narrow_to", "order_by", "partitions"),
    [
        pytest.param(
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Payment.id"), value=5),
            None,
            ("Payment.id",),
            False,
            id="direct-members",
        ),
        pytest.param(oa.TrueNode(), None, (), False, id="broad-projection"),
        pytest.param(
            oa.TrueNode(),
            ("CashPayment",),
            ("CashPayment.detail",),
            True,
            id="order-only-document-member",
        ),
    ],
)
def test_tph_partitioning_counts_only_the_root_rows_own_reads(
    node: oa.PredicateNode,
    narrow_to: tuple[str, ...] | None,
    order_by: tuple[str, ...],
    partitions: bool,
) -> None:
    plan = _planned(DOCUMENT_LAYOUT, "Payment", node, narrow_to=narrow_to, order_by=order_by)
    assert plan.requires_tph_partition is partitions
    if not partitions:
        assert list(plan.root_scopes) == [None]


def _kennel_model() -> Metamodel:
    """A table-per-hierarchy family under one Structured Column whose ``Dog``
    alone carries a scalar collection and two Value Object occurrences."""
    string: dict[str, object] = {"name": "name", "type": "string"}
    return accepted_model(
        {
            "entities": [
                {
                    "name": "Animal",
                    "namespace": "probe",
                    "table": "animal",
                    "layout": {"document": {"column": "payload"}},
                    "inheritance": {
                        "role": "root",
                        "strategy": "table-per-hierarchy",
                        "tag": {"column": "kind"},
                    },
                    "attributes": [{"name": "id", "type": "int64", "primaryKey": True}],
                },
                {
                    "name": "Dog",
                    "namespace": "probe",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": "probe.Animal",
                        "tagValue": "dog",
                    },
                    "attributes": [{"name": "tricks", "type": "string", "multiplicity": "many"}],
                    "valueObjects": [
                        {"name": "collar", "nullable": True, "attributes": [string]},
                        {"name": "toys", "multiplicity": "many", "attributes": [string]},
                    ],
                },
                {
                    "name": "Cat",
                    "namespace": "probe",
                    "inheritance": {
                        "role": "concrete-subtype",
                        "parent": "probe.Animal",
                        "tagValue": "cat",
                    },
                    "attributes": [{"name": "indoor", "type": "boolean", "nullable": True}],
                },
            ]
        }
    )


@pytest.mark.parametrize(
    ("operand", "partitions"),
    [
        pytest.param(oa.Quantifier("any", "Dog.tricks"), True, id="scalar-collection"),
        pytest.param(oa.Quantifier("none", "Dog.toys"), True, id="value-object-collection"),
        pytest.param(oa.Presence("exists", "Dog.collar"), True, id="object-presence"),
        pytest.param(_eq("Dog.collar.name"), True, id="value-object-leaf"),
        pytest.param(
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Animal.id"), value=1),
            False,
            id="direct-member",
        ),
    ],
)
def test_a_variant_document_read_at_the_root_row_partitions_the_family(
    operand: oa.PredicateNode, partitions: bool
) -> None:
    family = _kennel_model()
    plan = _planned(family, "Animal", oa.Narrow(to=("Dog",), operand=operand))
    assert plan.requires_tph_partition is partitions
    assert list(plan.root_scopes) == (_concretes(family, "Cat", "Dog") if partitions else [None])


@pytest.mark.parametrize(
    ("root", "node"),
    [
        pytest.param(
            "Book",
            oa.Comparison(op="greaterThan", subject=oa.FieldSubject("Book.pages"), value=100),
            id="table-per-concrete-subtype-concrete",
        ),
        pytest.param("Traveler", _eq("Traveler.displayName"), id="standalone"),
    ],
)
def test_a_single_table_read_outside_table_per_hierarchy_never_partitions(
    root: str, node: oa.PredicateNode
) -> None:
    # `Book.pages` is a document member its sibling `Film` lacks, which would
    # partition a table-per-hierarchy read; sharing its physical record does not
    # make this read one.
    plan, shape = _planned_shape(DOCUMENT_LAYOUT, root, node)
    assert isinstance(shape, SingleTableReadPlan)
    assert shape.tag_guard is None
    assert not plan.requires_tph_partition
    assert list(plan.root_scopes) == [None]
