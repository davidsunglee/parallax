"""What a unit of work reads through its row acquisition and makes of the rows
(`m-unit-work`), over an in-memory acquisition: predicate routing, selection
evidence, and target cardinality and revision, without SQL or a database."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance import models
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import inheritance, opt_lock
from parallax.core import predicate as predicate_algebra
from parallax.core.execution._planning import build_write_planner
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import EntityIdentity, Metamodel
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    Concurrency,
    KeyedWrite,
    PredicateMutation,
    PredicateSelection,
    PredicateWrite,
    TargetWrite,
    TransactionSettings,
    UnitOfWork,
    WriteAssignment,
    WriteBatchReason,
    WritePreconditionError,
)
from parallax.core.unit_work.acquisition import (
    RowConsumer,
    RowReadRequest,
    SelectionReadRequest,
    TargetReadRequest,
    consume_selection,
    consume_target,
)
from parallax.core.unit_work.instructions import (
    PreparedPredicateWrite,
    PreparedTargetWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core.unit_work.materialized import VersionedEvidence
from parallax.core.unit_work.uow import BindDeferredRange, ReportUnitCompletion
from parallax.core.write_plan import ObjectKey, PredecessorRow, PredecessorRows, WritePlan
from parallax.core.write_plan.steps import UNVERSIONED, PlannedDelete
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit.core.unit_work._acquired_rows_support import HeldRows

_MODELS = models.load_models()
_ACCOUNT: Final = _MODELS["account"]
_PERSON: Final = _MODELS["person"]
_BALANCE: Final = _MODELS["balance"]
_ABSENT: Final = object()


@dataclass(slots=True)
class _Flushes:
    """Records what each flush planned, entering each in ``log`` beside the row
    reads it orders against."""

    log: list[str]
    plans: list[WritePlan] = field(default_factory=list[WritePlan])

    def __call__(
        self,
        plan: WritePlan,
        /,
        *,
        trigger: WriteBatchReason,
        bind_deferred: BindDeferredRange,
        completed: ReportUnitCompletion,
    ) -> None:
        del bind_deferred
        self.log.append(f"flush:{trigger}")
        self.plans.append(plan)
        for unit in plan.units:
            completed(unit, None)


@dataclass(slots=True)
class _Logged:
    """``held``'s answers, each read entered in ``log`` as it is asked for."""

    held: HeldRows
    log: list[str]

    def __call__[Request: RowReadRequest, Result](
        self, request: Request, consumer: RowConsumer[Request, Result], /
    ) -> Result:
        self.log.append(f"read:{type(request).__name__}")
        return self.held(request, consumer)


def _uow(
    meta: Metamodel,
    rows: _Logged | HeldRows | None = None,
    *,
    concurrency: Concurrency = "optimistic",
    log: list[str] | None = None,
) -> tuple[UnitOfWork, _Flushes]:
    flushes = _Flushes([] if log is None else log)
    uow = UnitOfWork(
        settings=TransactionSettings(concurrency=concurrency),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=meta,
        flush_executor=flushes,
        acquire_rows=NO_ROW_READS if rows is None else rows,
        planner=build_write_planner(meta),
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(meta).required_key,
    )
    return uow, flushes


def _selection(meta: Metamodel, entity: str) -> EntityMemberSelection:
    view = inheritance.view(meta).entity(EntityIdentity("parallax.compatibility", entity))
    assert view is not None
    return view.member_selection


def _account(account_id: int, *, version: int = 3) -> PredecessorRow:
    return PredecessorRow(
        members={"id": account_id, "owner": "Ada", "balance": Decimal("100.00"), "version": version}
    )


def _person(person_id: int) -> PredecessorRow:
    return PredecessorRow(members={"id": person_id, "name": "Ada"})


def _predicate(
    meta: Metamodel,
    entity: str,
    mutation: PredicateMutation = "delete",
    assignments: Sequence[WriteAssignment] = (),
) -> PreparedPredicateWrite:
    return prepare_typed_write(
        PredicateWrite(
            mutation,
            PredicateSelection(entity, predicate_algebra.Comparison("eq", f"{entity}.id", 1)),
            tuple(assignments),
        ),
        meta,
    )


def _account_patch(*, version: int = 3) -> PreparedTargetWrite:
    return prepare_wire_write(
        TargetWrite("amend", "Account", {"id": 1, "balance": "9.00"}, if_version=version),
        _ACCOUNT,
    )


def _person_patch() -> PreparedTargetWrite:
    return prepare_wire_write(TargetWrite("amend", "Person", {"id": 1, "name": "Zed"}), _PERSON)


# --------------------------------------------------------------------------- #
# Predicate routing: decided once, by the unit of work.                       #
# --------------------------------------------------------------------------- #
def test_an_unversioned_non_temporal_predicate_write_is_routed_readless_and_reads_nothing() -> None:
    uow, flushes = _uow(_PERSON)
    uow.buffer_predicate(_predicate(_PERSON, "Person"))
    uow.flush(trigger="pre_commit")
    (plan,) = flushes.plans
    (step,) = plan.steps
    assert isinstance(step, PlannedDelete)
    assert step.concurrency is UNVERSIONED


def test_a_versioned_predicate_write_reads_its_selection_once_after_pending_writes_flush() -> None:
    log: list[str] = []
    held = HeldRows(_ACCOUNT, [_account(1)])
    uow, _flushes = _uow(_ACCOUNT, _Logged(held, log), log=log)
    insert = prepare_typed_write(
        KeyedWrite("insert", "Account", ({"id": 7, "owner": "Newton", "balance": 5},)), _ACCOUNT
    )
    uow.buffer(insert)
    uow.buffer_predicate(_predicate(_ACCOUNT, "Account"))
    assert log == ["flush:read_dependency", "read:SelectionReadRequest"]
    (request,) = held.requests
    assert isinstance(request, SelectionReadRequest)
    assert not request.predecessors
    assert request.version_position == _selection(_ACCOUNT, "Account").shape.position("version")


def test_a_temporal_predicate_write_reads_its_selected_rows_whole() -> None:
    held = HeldRows(_BALANCE)
    uow, flushes = _uow(_BALANCE, held)
    uow.buffer_predicate(_predicate(_BALANCE, "Balance", "terminate"))
    (request,) = held.requests
    assert isinstance(request, SelectionReadRequest)
    assert request.predecessors
    # A selection leaving no row buffers nothing.
    uow.flush(trigger="pre_commit")
    assert flushes.plans == []


# --------------------------------------------------------------------------- #
# Selection evidence: adopted by reference, documents by original position.   #
# --------------------------------------------------------------------------- #
def _balance_rows(*values: str) -> list[tuple[object, ...]]:
    selection = _selection(_BALANCE, "Balance")
    position = selection.shape.position("value")
    assert position is not None
    rows: list[tuple[object, ...]] = []
    for value in values:
        cells: list[object] = [_ABSENT] * len(selection.bindings)
        cells[position] = Decimal(value)
        rows.append(tuple(cells))
    return rows


def _balance_selection_request() -> SelectionReadRequest:
    write = _predicate(
        _BALANCE, "Balance", "amend", (WriteAssignment("Balance.value", Decimal("5.00")),)
    )
    selection = _selection(_BALANCE, "Balance")
    key = selection.shape.position("id")
    assert key is not None
    return SelectionReadRequest(write, key_position=key, version_position=None)


def test_a_filtered_selection_adopts_each_surviving_row_and_its_own_document() -> None:
    rows = _balance_rows("5.00", "6.00", "7.00")
    documents = [object(), object(), object()]
    evidence = consume_selection(
        _balance_selection_request(),
        _selection(_BALANCE, "Balance"),
        iter(rows),
        _ABSENT,
        documents,
        len(rows),
    )
    assert isinstance(evidence, PredecessorRows)
    # The no-op first row is eliminated; each survivor keeps its own raw
    # document, by its original position rather than its place in the evidence.
    assert [evidence.rows[index] for index in range(len(evidence))] == rows[1:]
    assert all(evidence.rows[index] is rows[index + 1] for index in range(len(evidence)))
    assert [evidence.document(index) for index in range(len(evidence))] == documents[1:]
    assert evidence.absent is _ABSENT


def test_a_selection_without_a_document_column_carries_no_documents() -> None:
    rows = _balance_rows("6.00")
    evidence = consume_selection(
        _balance_selection_request(),
        _selection(_BALANCE, "Balance"),
        iter(rows),
        _ABSENT,
        None,
        len(rows),
    )
    assert isinstance(evidence, PredecessorRows)
    assert evidence.documents is None


def test_a_versioned_selection_keeps_each_rows_key_and_observed_version() -> None:
    held = HeldRows(_ACCOUNT, [_account(1, version=4), _account(2, version=9)])
    uow, flushes = _uow(_ACCOUNT, held)
    uow.buffer_predicate(_predicate(_ACCOUNT, "Account"))
    uow.flush(trigger="pre_commit")
    (plan,) = flushes.plans
    assert len(plan.steps) == 2
    (request,) = held.requests
    assert isinstance(request, SelectionReadRequest)
    rows = held.rows
    selection = _selection(_ACCOUNT, "Account")
    evidence = consume_selection(
        request, selection, iter(_positional(selection, rows)), _ABSENT, None, len(rows)
    )
    assert isinstance(evidence, VersionedEvidence)
    assert (list(evidence.keys), list(evidence.versions)) == ([1, 2], [4, 9])


def _positional(
    selection: EntityMemberSelection, rows: Sequence[PredecessorRow]
) -> list[tuple[object, ...]]:
    return [
        tuple(row.members.get(member.name, _ABSENT) for member in selection.shape.members)
        for row in rows
    ]


# --------------------------------------------------------------------------- #
# Target acquisition: the root count decides first.                            #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class _Rows:
    """Member rows that record whether anything asked for them."""

    rows: Sequence[tuple[object, ...]]
    started: bool = False

    def __iter__(self) -> Iterator[tuple[object, ...]]:
        self.started = True
        yield from self.rows


@pytest.mark.parametrize("count", [0, 2, 3])
def test_a_target_read_without_a_unique_root_requests_no_row(count: int) -> None:
    rows = _Rows([(1,)] * count)
    answered = consume_target(
        _target_request(), _selection(_ACCOUNT, "Account"), iter(rows), _ABSENT, None, count
    )
    assert answered == (count, None)
    assert not rows.started


def test_a_target_read_with_a_unique_root_answers_that_row() -> None:
    row = (1, "Ada", Decimal("100.00"), 3)
    rows = _Rows([row])
    count, answered = consume_target(
        _target_request(), _selection(_ACCOUNT, "Account"), iter(rows), _ABSENT, None, 1
    )
    assert (count, answered) == (1, row)
    assert answered is row


def _target_request() -> TargetReadRequest:
    prepared = _account_patch()
    return TargetReadRequest(
        prepared.target, ObjectKey(prepared.target.identity, (("id", 1),)), None
    )


def test_a_locking_target_reading_several_rows_is_corruption_with_their_exact_count() -> None:
    held = HeldRows(_ACCOUNT, [_account(1), _account(1), _account(1)])
    uow, flushes = _uow(_ACCOUNT, held, concurrency="locking")
    with pytest.raises(CardinalityCorruptionError) as corrupt:
        uow.buffer_target(_account_patch())
    assert (corrupt.value.expected, corrupt.value.actual) == (1, 3)
    uow.flush(trigger="pre_commit")
    assert flushes.plans == []


def test_a_locking_target_reading_no_row_fails_its_callers_precondition() -> None:
    uow, _flushes = _uow(_ACCOUNT, HeldRows(_ACCOUNT), concurrency="locking")
    with pytest.raises(WritePreconditionError):
        uow.buffer_target(_account_patch())


@pytest.mark.parametrize(("stored", "admitted"), [(3, True), (4, False)])
def test_a_locking_target_compares_the_unique_rows_version_with_its_callers(
    stored: int, admitted: bool
) -> None:
    held = HeldRows(_ACCOUNT, [_account(1, version=stored)])
    uow, flushes = _uow(_ACCOUNT, held, concurrency="locking")
    if admitted:
        uow.buffer_target(_account_patch())
        uow.flush(trigger="pre_commit")
        assert len(flushes.plans) == 1
    else:
        with pytest.raises(WritePreconditionError):
            uow.buffer_target(_account_patch())
    (request,) = held.requests
    assert isinstance(request, TargetReadRequest)


def test_an_effectively_optimistic_target_reads_nothing() -> None:
    uow, flushes = _uow(_ACCOUNT, concurrency="optimistic")
    uow.buffer_target(_account_patch())
    uow.flush(trigger="pre_commit")
    assert len(flushes.plans) == 1


@pytest.mark.parametrize("concurrency", ["optimistic", "locking"])
def test_an_unversioned_non_temporal_target_participates_under_either_preference(
    concurrency: Concurrency,
) -> None:
    held = HeldRows(_PERSON, [_person(1)])
    uow, _flushes = _uow(_PERSON, held, concurrency=concurrency)
    uow.buffer_target(_person_patch())
    (request,) = held.requests
    assert isinstance(request, TargetReadRequest)
