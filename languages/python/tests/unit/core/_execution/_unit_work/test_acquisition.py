"""What a unit of work reads through its row acquisition and makes of the rows
(`m-unit-work`), over an in-memory acquisition: a predicate write reads nothing,
and a target read's cardinality and revision, without SQL or a database."""

from __future__ import annotations

import contextlib
import datetime as dt
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

import pytest

from parallax.conformance import models
from parallax.conformance._simulated_write_steps import SimulatedWriteSteps
from parallax.conformance.scripted_clock import FixedClock
from parallax.core import inheritance, opt_lock
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work import acquisition as acquisition_module
from parallax.core._execution._unit_work.acquisition import (
    CoverageReadRequest,
    CoverageTerm,
    RowConsumer,
    RowRequest,
    TargetReadRequest,
    consume_coverage,
    consume_coverage_by_key,
    consume_target,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.core._execution._unit_work.uow import FlushScope
from parallax.core.dialect import POSTGRES
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    Concurrency,
    FlushTrigger,
    PredicateMutation,
    PredicateSelection,
    PredicateWriteInstruction,
    TargetWriteInstruction,
    TransactionSettings,
    UnitOfWork,
    WriteAssignment,
    WritePreconditionError,
)
from parallax.core.write_plan import ObjectKey, PredecessorRow
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

_MODELS = models.load_models()
_ACCOUNT: Final = _MODELS["account"]
_PERSON: Final = _MODELS["person"]
_ABSENT: Final = object()


@dataclass(slots=True)
class _Flushes:
    """Each flush's activity entered in ``log`` beside the row reads it
    orders against, and every statement its spans lowered to."""

    log: list[str]
    simulated: SimulatedWriteSteps
    opened: int = 0

    def __call__(self, trigger: FlushTrigger, /) -> FlushScope:
        self.opened += 1
        self.log.append(f"flush:{trigger}")
        return contextlib.nullcontext()


@dataclass(slots=True)
class _Logged:
    """``held``'s answers, each read entered in ``log`` as it is asked for."""

    held: HeldRows
    log: list[str]

    def __call__[Request: RowRequest, Result](
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
    planner = build_write_planner(meta)
    flushes = _Flushes(
        [] if log is None else log, SimulatedWriteSteps(planner.payloads, meta, POSTGRES)
    )
    uow = UnitOfWork(
        lifetime=TxnAttemptLifetime(),
        settings=TransactionSettings(concurrency=concurrency),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=meta,
        execute_write_steps=flushes.simulated,
        execute_counted_step=flushes.simulated.counted,
        acquire_rows=NO_ROW_READS if rows is None else rows,
        planner=planner,
        actor_identity=TEST_ACTOR_IDENTITY,
        evidence_policy_for=opt_lock.view(meta).required_key,
        flush_opening=flushes,
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


def _predicate(
    meta: Metamodel,
    entity: str,
    mutation: PredicateMutation = "delete",
    assignments: Sequence[WriteAssignment] = (),
) -> PreparedPredicateInstruction:
    return prepare_typed_write(
        PredicateWriteInstruction(
            mutation,
            PredicateSelection(
                entity,
                predicate_algebra.Comparison(
                    "eq", predicate_algebra.FieldSubject(f"{entity}.id"), 1
                ),
            ),
            tuple(assignments),
        ),
        meta,
    )


def _account_patch(*, version: int = 3) -> PreparedTargetInstruction:
    return prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": 1, "balance": "9.00"}, if_version=version
        ),
        _ACCOUNT,
    )


# --------------------------------------------------------------------------- #
# A predicate write is readless.                                              #
# --------------------------------------------------------------------------- #
def test_a_predicate_write_executes_readless_and_reads_nothing() -> None:
    uow, flushes = _uow(_PERSON)
    uow.execute_predicate(_predicate(_PERSON, "Person"))
    # One unconditioned delete of the matching rows, which nothing read.
    (statement,) = flushes.simulated.statements
    assert statement.sql == "delete from person where id = ?"


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
    assert answered == (count, None, None)
    assert not rows.started


@pytest.mark.parametrize("documents", [None, ["raw"]], ids=["columns", "document"])
def test_a_target_read_with_a_unique_root_answers_that_row_and_its_document(
    documents: list[object] | None,
) -> None:
    row = (1, "Ada", Decimal("100.00"), 3)
    rows = _Rows([row])
    count, answered, document = consume_target(
        _target_request(), _selection(_ACCOUNT, "Account"), iter(rows), _ABSENT, documents, 1
    )
    assert (count, answered) == (1, row)
    assert answered is row
    assert document is (None if documents is None else documents[0])


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
    assert flushes.opened == 0


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
        assert len(flushes.simulated.statements) == 1
    else:
        with pytest.raises(WritePreconditionError):
            uow.buffer_target(_account_patch())
    (request,) = held.requests
    assert isinstance(request, TargetReadRequest)


def test_an_effectively_optimistic_target_reads_nothing() -> None:
    uow, flushes = _uow(_ACCOUNT, concurrency="optimistic")
    uow.buffer_target(_account_patch())
    uow.flush(trigger="pre_commit")
    assert len(flushes.simulated.statements) == 1


# --------------------------------------------------------------------------- #
# A consumer keeps no row or document it was handed once it fails.            #
# --------------------------------------------------------------------------- #
class _Unjudged(Exception):
    pass


def _failing_after(rows: Sequence[tuple[object, ...]], after: int) -> Iterator[tuple[object, ...]]:
    yield from rows[:after]
    raise _Unjudged


@pytest.mark.parametrize("coverage", [False, True], ids=["target", "coverage"])
def test_a_consumer_a_row_fails_in_holds_none_of_the_rows_or_documents_it_was_handed(
    coverage: bool,
) -> None:
    rows = [(1, "Ada", Decimal("100.00"), 3), (2, "Bea", Decimal("200.00"), 3)]
    documents: list[object | None] = ["raw-1", "raw-2"]
    request = _target_request()
    selection = _selection(_ACCOUNT, "Account")
    with pytest.raises(_Unjudged) as raised:
        if coverage:
            coverage_request = CoverageReadRequest(
                request.entity, _key(request), (CoverageTerm(1, ()),), locking=False
            )
            consume_coverage(
                coverage_request, selection, _failing_after(rows, 1), _ABSENT, documents, 2
            )
        else:
            consume_target(request, selection, _failing_after(rows, 0), _ABSENT, documents, 1)
    consumer = frames(raised.value.__traceback__, module=acquisition_module.__file__)
    assert consumer
    assert not reaches(consumer, documents)
    assert not reaches(consumer, rows[0])


def _key(request: TargetReadRequest) -> AttributeIdentity:
    ((name, _value),) = request.key.primary_key
    return AttributeIdentity(request.entity.identity, name)


# --------------------------------------------------------------------------- #
# A coverage read of several objects: each row goes to the object whose key   #
# it holds.                                                                    #
# --------------------------------------------------------------------------- #
def _shared_request() -> CoverageReadRequest:
    request = _target_request()
    terms = (CoverageTerm(1, ()), CoverageTerm(2, ()), CoverageTerm(3, ()))
    return CoverageReadRequest(request.entity, _key(request), terms, locking=False)


def test_a_shared_reads_rows_and_documents_go_to_the_object_each_row_holds_the_key_of() -> None:
    rows = [
        (2, "Bea", Decimal("200.00"), 3),
        (1, "Ada", Decimal("100.00"), 3),
        (2, "Bea", Decimal("200.00"), 3),
        (2, "Cy", Decimal("300.00"), 3),
    ]
    documents: list[object | None] = ["raw-2a", "raw-1", "raw-2a", "raw-2b"]
    selection = _selection(_ACCOUNT, "Account")
    evidence = consume_coverage_by_key(
        _shared_request(), selection, iter(rows), _ABSENT, documents, len(rows)
    )
    # Object 3 returned no row and has no evidence; a row read twice is kept twice.
    assert set(evidence) == {1, 2}
    first, second = evidence[1], evidence[2]
    assert [first.rows[index] for index in range(len(first))] == [rows[1]]
    assert [first.document(index) for index in range(len(first))] == ["raw-1"]
    assert [second.rows[index] for index in range(len(second))] == [rows[0], rows[2], rows[3]]
    assert [second.document(index) for index in range(len(second))] == [
        "raw-2a",
        "raw-2a",
        "raw-2b",
    ]
    # Each row is adopted by reference.
    assert second.rows[0] is rows[0]


def test_a_shared_read_returning_nothing_is_no_objects_evidence() -> None:
    selection = _selection(_ACCOUNT, "Account")
    assert consume_coverage_by_key(_shared_request(), selection, iter(()), _ABSENT, None, 0) == {}


def test_a_shared_reads_consumer_a_row_fails_in_holds_none_of_the_rows_or_documents() -> None:
    rows = [(1, "Ada", Decimal("100.00"), 3), (2, "Bea", Decimal("200.00"), 3)]
    documents: list[object | None] = ["raw-1", "raw-2"]
    selection = _selection(_ACCOUNT, "Account")
    with pytest.raises(_Unjudged) as raised:
        consume_coverage_by_key(
            _shared_request(), selection, _failing_after(rows, 2), _ABSENT, documents, 2
        )
    consumer = frames(raised.value.__traceback__, module=acquisition_module.__file__)
    assert consumer
    assert not reaches(consumer, documents)
    assert not any(reaches(consumer, row) for row in rows)
