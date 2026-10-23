"""Statement planning decisions, read without rendering SQL."""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from parallax.conformance.models import accepted_model
from parallax.core import inheritance, storage_layout
from parallax.core import predicate as oa
from parallax.core.deep_fetch import PlannedEntityQuery, ResolvedReadProjection
from parallax.core.dialect import POSTGRES
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
from parallax.core.sql_gen import _compile as sql_compile
from parallax.core.sql_gen import _context, _planning
from parallax.core.sql_gen._inheritance import plan_inheritance_read
from parallax.core.sql_gen._planning import (
    NO_CANDIDATE,
    REACHED_ROW,
    BranchSelection,
    CandidateExistence,
    ConfinedScalarEvaluation,
    Continuation,
    EvaluationContext,
    JoinedTargetMatch,
    LexicalScopePlan,
    OwnerResultEvaluation,
    OwnerResultsRef,
    SharedRowEvaluation,
    SharedSourceRef,
    StatementPlan,
    TargetSelection,
    UnsharedEvaluation,
    WriteFilterForm,
    plan_relationship_candidates,
    plan_statement,
    shared_relationship_is_eligible,
)
from parallax.core.temporal_read import Bitemporal
from parallax.core.temporal_read import view as temporal_view
from tests._support.sql import (
    compile_read,
    compile_write_predicate,
    read_position,
    resolved_as_stated,
)
from tests.unit._corpus_model_support import model, target
from tests.unit.core.sql_gen._badge_model_support import badge_model, temporal_badge_model
from tests.unit.core.sql_gen._dormant_model_support import dormant_target_model
from tests.unit.core.sql_gen._plan_reuse_support import record_plan_reuse

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
    facet, storage = inheritance.view(model), storage_layout.view(model)
    seen = dataclasses.replace(hop, temporal_visibility=visibility)
    candidates = plan_relationship_candidates(
        seen, position=None, meta=model, facet=facet, storage=storage
    )
    return shared_relationship_is_eligible(seen, candidates, facet=facet, storage=storage)


_INSTANT = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


def _seen(model: Metamodel, name: str, *, valid: bool, tx: bool) -> TemporalPerspective:
    """``name``'s visibility: Latest on each axis flagged, else At one instant."""
    shape = temporal_view(model).shape(target(model, name).identity)
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


@pytest.mark.parametrize("latest", [True, False], ids=["latest", "at"])
def test_a_temporal_hop_off_its_logical_key_needs_a_unique_key_the_correlation_fixes(
    latest: bool,
) -> None:
    for unique in (True, False):
        family = temporal_badge_model(unique=unique)
        hop = _to_one(family, "Holder", "Holder.badge")
        visibility = _seen(family, "Badge", valid=latest, tx=latest)
        assert _eligible(family, hop, visibility) is unique


def test_several_physical_candidates_are_never_proven_unique() -> None:
    hop = _to_many(DOCUMENT, "Folder", "Folder.documents")
    facet, storage = inheritance.view(DOCUMENT), storage_layout.view(DOCUMENT)
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
    entity = target(family, root)
    facet, storage = inheritance.view(family), storage_layout.view(family)
    narrowed = (
        None if narrow_to is None else tuple(target(family, name).identity for name in narrow_to)
    )
    predicate = resolved_as_stated(oa.validate_predicate(entity, node, family), family, entity)
    read = (
        None
        if entity.inheritance is None
        else plan_inheritance_read(
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
            None,
        )
    )
    return plan_statement(
        predicate,
        evaluation_context=context,
        entity=entity,
        meta=family,
        facet=facet,
        storage=storage,
        inheritance_read=read,
        order_terms=tuple(_order_term(family, name) for name in order_by),
    )


def _order_term(family: Metamodel, reference: str) -> ResolvedOrderTerm:
    owner, _, name = reference.rpartition(".")
    view = inheritance.view(family).entity(target(family, owner).identity)
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


def test_every_rendered_occurrence_is_placed_explicitly_and_boolean_slots_are_not() -> None:
    op = oa.And(operands=(_eq("Basket.label"), oa.Not(_eq("Basket.owner.name"))))
    plan = _planned(COLLECTIONS, "Basket", op)
    root = _root(plan)
    assert set(root.placements) == {(0,), (1, 0)}
    assert root.placements[(0,)] == _AT_ROW
    assert root.placements[(1, 0)] == SharedRowEvaluation(
        SharedSourceRef(root.scope_id, 0), REACHED_ROW
    )
    assert plan.write_filter_form is None
    assert not plan.requires_tph_partition


def test_sources_follow_first_use_with_a_common_prefix_opened_once() -> None:
    op = oa.Or(operands=(_eq("Basket.owner.manager.name"), _eq("Basket.owner.name")))
    root = _root(_planned(COLLECTIONS, "Basket", op))
    owner = SharedSourceRef(root.scope_id, 0)
    assert [source.parent for source in root.sources] == [None, owner]
    assert [source.relationship.identity.name for source in root.sources] == ["owner", "manager"]
    assert root.placements[(0,)] == SharedRowEvaluation(
        SharedSourceRef(root.scope_id, 1), REACHED_ROW
    )
    assert root.placements[(1,)] == SharedRowEvaluation(owner, REACHED_ROW)


def test_a_presence_reuses_a_target_a_later_sibling_shares() -> None:
    op = oa.And(operands=(oa.Presence("exists", "Basket.owner"), _eq("Basket.owner.name")))
    root = _root(_planned(COLLECTIONS, "Basket", op))
    assert len(root.sources) == 1
    assert root.placements[(0,)] == SharedRowEvaluation(
        SharedSourceRef(root.scope_id, 0), JoinedTargetMatch(None)
    )


def test_a_match_alone_shares_nothing_and_plans_its_candidate_operand() -> None:
    plan = _planned(COLLECTIONS, "Basket", oa.Presence("exists", "Basket.owner", _eq("name")))
    root = _root(plan)
    assert root.sources == ()
    placement = root.placements[()]
    assert isinstance(placement, UnsharedEvaluation)
    (existence,) = placement.continuation.terminals
    assert isinstance(existence, CandidateExistence)
    (candidate,) = existence.candidates
    assert _scope(plan, candidate.operand_scope).placements == {(): _AT_ROW}


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
        facet=inheritance.view(family),
        storage=storage_layout.view(family),
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


def test_an_unproven_hop_continues_confined_past_its_shared_prefix() -> None:
    plan = _planned(TRAVERSAL, "Ticket", _eq("Ticket.parking.vehicle.maker"))
    root = _root(plan)
    placement = root.placements[()]
    assert isinstance(placement, ConfinedScalarEvaluation)
    assert placement.prefix == SharedSourceRef(root.scope_id, 0)
    (hop,) = placement.continuation.hops
    assert len(hop.candidates.branches) == 2
    assert placement.continuation.terminals == (REACHED_ROW, REACHED_ROW)


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


@pytest.mark.parametrize("strategy", ["tph", "tpcs"])
def test_an_empty_target_keeps_the_hops_before_it_and_plans_nothing_past_it(
    strategy: Any,
) -> None:
    family = dormant_target_model(strategy)
    field = _root(_planned(family, "Holder", _eq("Holder.next.empty.title"))).placements[()]
    assert isinstance(field, UnsharedEvaluation)
    assert [hop.relationship.identity.name for hop in field.continuation.hops] == ["next"]
    assert field.continuation.terminals == (NO_CANDIDATE,)
    plan = _planned(family, "Holder", oa.Quantifier("any", "Holder.empties", _eq("title")))
    collection = _root(plan).placements[()]
    assert collection == UnsharedEvaluation(Continuation((), (CandidateExistence(()),)))
    assert len(plan.lexical_scopes) == 1


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


def test_a_write_filter_plans_only_the_form_its_root_selects() -> None:
    direct = _planned(
        COLLECTIONS,
        "Basket",
        oa.Presence("exists", "Basket.owner", _eq("manager.name")),
        context=EvaluationContext.WRITE_FILTER,
    )
    assert direct.write_filter_form is WriteFilterForm.DIRECT_PREDICATE
    placement = _root(direct).placements[()]
    assert isinstance(placement, UnsharedEvaluation)
    (existence,) = placement.continuation.terminals
    assert isinstance(existence, CandidateExistence)
    (candidate,) = existence.candidates
    assert _scope(direct, candidate.operand_scope).sources == ()
    assert len(direct.lexical_scopes) == 2
    keyed = _planned(
        COLLECTIONS, "Basket", _eq("Basket.owner.name"), context=EvaluationContext.WRITE_FILTER
    )
    assert keyed.write_filter_form is WriteFilterForm.PRIMARY_KEY_SUBQUERY
    assert len(_root(keyed).sources) == 1
    assert dict(keyed.root_scopes) == {None: 0}


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
    plan = _planned(DOCUMENT_LAYOUT, "Payment", _CARD_OR_CASH)
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


def test_a_statement_plan_and_its_records_are_read_only() -> None:
    plan = _planned(COLLECTIONS, "Basket", _eq("Basket.owner.name"))
    root = _root(plan)
    with pytest.raises(TypeError):
        root.placements[(9,)] = _AT_ROW  # type: ignore[index]
    with pytest.raises(TypeError):
        plan.root_scopes[None] = 1  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        root.sources[0].parent = None  # type: ignore[misc]


@pytest.fixture
def planning_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, bool]]]:
    """Every candidate, eligibility, alias, and bind call, and whether a
    production ``plan_statement`` invocation was running at the time."""
    calls: list[tuple[str, bool]] = []
    planning = [False]

    def recorded[**P, R](name: str, function: Callable[P, R]) -> Callable[P, R]:
        def call(*args: P.args, **kwargs: P.kwargs) -> R:
            calls.append((name, planning[0]))
            return function(*args, **kwargs)

        return call

    real_plan = _planning.plan_statement

    def plan(*args: Any, **kwargs: Any) -> StatementPlan:
        planning[0] = True
        try:
            return real_plan(*args, **kwargs)
        finally:
            planning[0] = False

    monkeypatch.setattr(sql_compile, "_plan_statement", plan)
    for name in ("plan_relationship_candidates", "shared_relationship_is_eligible"):
        monkeypatch.setattr(_planning, name, recorded(name, getattr(_planning, name)))
    builder = _context.StatementBuilder
    for name in ("next_alias", "next_relation_alias", "_append"):
        monkeypatch.setattr(builder, name, recorded(name, getattr(builder, name)))
    yield calls


def test_rendering_reads_planned_decisions_without_reentering_analysis(
    planning_calls: list[tuple[str, bool]],
) -> None:
    op = oa.And(
        operands=(
            _eq("Ticket.parking.vehicle.maker"),
            oa.Presence("exists", "Ticket.parking", oa.Presence("exists", "vehicle.dealer")),
        )
    )
    compile_read(op, TRAVERSAL, POSTGRES, target(TRAVERSAL, "Ticket"))
    compile_write_predicate(op, TRAVERSAL, POSTGRES, target(TRAVERSAL, "Ticket"))
    analysis = {"plan_relationship_candidates", "shared_relationship_is_eligible"}
    assert {name for name, _ in planning_calls} >= {*analysis, "next_alias", "_append"}
    assert all(during for name, during in planning_calls if name in analysis)
    assert not any(during for name, during in planning_calls if name not in analysis)


@pytest.mark.parametrize(
    ("op", "form", "roots"),
    [
        (_eq("Ticket.parking.vehicle.maker"), None, 1),
        (_eq("Ticket.id", 7), WriteFilterForm.DIRECT_PREDICATE, 0),
        (_eq("Ticket.parking.vehicle.maker"), WriteFilterForm.PRIMARY_KEY_SUBQUERY, 1),
    ],
    ids=["ordinary-read", "direct-write-filter", "key-selecting-write-filter"],
)
def test_each_compilation_plans_its_statement_once(
    op: oa.PredicateNode,
    form: WriteFilterForm | None,
    roots: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reuse = record_plan_reuse(monkeypatch)
    ticket = target(TRAVERSAL, "Ticket")
    if form is None:
        compile_read(op, TRAVERSAL, POSTGRES, ticket)
    else:
        compile_write_predicate(op, TRAVERSAL, POSTGRES, ticket)
    (plan,) = reuse.plans
    assert plan.write_filter_form is form
    assert [root.statement_plan for root in reuse.roots] == [plan] * roots


def test_rendering_leaves_its_statement_plan_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    plans: list[StatementPlan] = []
    real_plan = _planning.plan_statement

    def plan(*args: Any, **kwargs: Any) -> StatementPlan:
        plans.append(real_plan(*args, **kwargs))
        return plans[-1]

    monkeypatch.setattr(sql_compile, "_plan_statement", plan)
    op = oa.And(
        operands=(
            oa.Quantifier("any", "Basket.owner.tags", _TAGGED_N),
            oa.Presence("exists", "Basket.owner", _eq("manager.name")),
        )
    )
    compile_read(op, COLLECTIONS, POSTGRES, target(COLLECTIONS, "Basket"))
    (rendered,) = plans
    assert rendered == _planned(COLLECTIONS, "Basket", op)
