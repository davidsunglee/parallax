"""What a unit of work reads through its row acquisition and makes of the rows
(`m-unit-work`), over an in-memory acquisition: a target read's cardinality, which
object a shared read's rows go to, and what a failed consumer keeps, without SQL or a
database."""

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
from parallax.core import InternalError
from parallax.core._execution._planning import build_write_planner
from parallax.core._execution._transaction._lifetime import TxnAttemptLifetime
from parallax.core._execution._unit_work import row_acquisition as acquisition_module
from parallax.core._execution._unit_work.effects import CARDINALITY_CORRUPTION
from parallax.core._execution._unit_work.preparation import (
    WIRE,
    PreparedTargetInstruction,
)
from parallax.core._execution._unit_work.row_acquisition import (
    CompletionRequest,
    CoverageReadKey,
    CoverageReadRequest,
    CoverageTerm,
    TargetReadRequest,
    consume_completion,
    consume_coverage,
    consume_target,
)
from parallax.core._execution._unit_work.uow import FlushScope
from parallax.core.internal import inheritance
from parallax.core.internal.base import INFINITY
from parallax.core.internal.concurrency import ConcurrencyPreference
from parallax.core.internal.dialect import POSTGRES
from parallax.core.internal.inheritance import EntityMemberSelection
from parallax.core.internal.metamodel import AttributeIdentity, EntityIdentity, Metamodel
from parallax.core.internal.planned_step import ObjectKey, PredecessorRow
from parallax.core.internal.temporal_read import TimeInterval
from parallax.core.internal.unit_work import (
    FlushTrigger,
    TargetWriteInstruction,
    TransactionSettings,
    UnitOfWork,
)
from tests._support.bindings import bound_model
from tests._support.errors import raises_code
from tests._support.planner_probes import NO_ROW_READS, TEST_ACTOR_IDENTITY
from tests._support.write_preparation import prepare_instruction, write_preparation_of
from tests.unit._corpus_model_support import formed, records, target
from tests.unit.core._execution._reach_support import frames, reaches
from tests.unit.core._execution._unit_work._acquired_rows_support import HeldRows

_MODELS = models.load_models()
_ACCOUNT: Final = _MODELS["account"]
_ABSENT: Final = object()


@dataclass(slots=True)
class _Flushes:
    """Every flush opened, and every statement its spans lowered to."""

    simulated: SimulatedWriteSteps
    opened: int = 0

    def __call__(self, trigger: FlushTrigger, /) -> FlushScope:
        self.opened += 1
        return contextlib.nullcontext()


def _uow(
    meta: Metamodel,
    rows: HeldRows | None = None,
    *,
    concurrency: ConcurrencyPreference = "optimistic",
) -> tuple[UnitOfWork, _Flushes]:
    planner = build_write_planner(bound_model(meta))
    flushes = _Flushes(SimulatedWriteSteps(planner.payloads, bound_model(meta), POSTGRES))
    uow = UnitOfWork(
        lifetime=TxnAttemptLifetime(),
        settings=TransactionSettings(preference=concurrency),
        clock=FixedClock(dt.datetime(2024, 6, 1, tzinfo=dt.UTC)),
        meta=meta,
        execute_write_steps=flushes.simulated,
        execute_counted_step=flushes.simulated.counted,
        acquire_rows=NO_ROW_READS if rows is None else rows,
        planner=planner,
        actor_identity=TEST_ACTOR_IDENTITY,
        flush_opening=flushes,
    )
    return uow, flushes


def _selection(meta: Metamodel, entity: str) -> EntityMemberSelection:
    view = inheritance.inheritance_facet_of(meta).entity(
        EntityIdentity("parallax.compatibility", entity)
    )
    assert view is not None
    return view.member_selection


def _account(account_id: int) -> PredecessorRow:
    return PredecessorRow(
        members={"id": account_id, "owner": "Ada", "balance": Decimal("100.00"), "version": 3}
    )


def _account_patch() -> PreparedTargetInstruction:
    return prepare_instruction(
        TargetWriteInstruction("amend", "Account", {"id": 1, "balance": "9.00"}, if_version=3),
        write_preparation_of(_ACCOUNT),
        WIRE,
    )


# --------------------------------------------------------------------------- #
# A coverage term names at least one uncovered part.                          #
# --------------------------------------------------------------------------- #
_JAN: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("windows", "parts"),
    [
        (None, 1),
        ((TimeInterval(_JAN, _MAR),), 1),
        ((TimeInterval(_JAN, _MAR), TimeInterval(_MAR + dt.timedelta(days=1), INFINITY)), 2),
    ],
    ids=["current-row", "one-window", "two-windows"],
)
def test_a_coverage_term_counts_one_part_per_window_and_one_for_a_current_row(
    windows: tuple[TimeInterval, ...] | None, parts: int
) -> None:
    assert CoverageTerm(1, windows).part_count == parts


def test_a_coverage_term_naming_no_part_is_refused() -> None:
    with pytest.raises(ValueError, match="at least one window"):
        CoverageTerm(1, ())


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
    with raises_code(InternalError, CARDINALITY_CORRUPTION) as corrupt:
        uow.buffer_target(_account_patch())
    assert "affected 3 row(s), expected 1" in str(corrupt.value)
    uow.flush(trigger="pre_commit")
    assert flushes.opened == 0


# --------------------------------------------------------------------------- #
# A consumer keeps no row or document it was handed once it fails.            #
# --------------------------------------------------------------------------- #
class _Unjudged(Exception):
    pass


def _failing_after(rows: Sequence[tuple[object, ...]], after: int) -> Iterator[tuple[object, ...]]:
    yield from rows[:after]
    raise _Unjudged


@pytest.mark.parametrize("completion", [False, True], ids=["target", "completion"])
def test_a_consumer_a_row_fails_in_holds_none_of_the_rows_or_documents_it_was_handed(
    completion: bool,
) -> None:
    rows = [(1, "Ada", Decimal("100.00"), 3), (2, "Bea", Decimal("200.00"), 3)]
    documents: list[object | None] = ["raw-1", "raw-2"]
    request = _target_request()
    selection = _selection(_ACCOUNT, "Account")
    with pytest.raises(_Unjudged) as raised:
        if completion:
            # A completion's consumer is handed judged rows, not the raw rows
            # the request carries.
            raw = tuple((*row,) for row in rows)
            completing = CompletionRequest(request.entity, _key(request), raw, tuple(documents))
            consume_completion(
                completing, selection, _failing_after(rows, 1), _ABSENT, documents, 2
            )
        else:
            consume_target(request, selection, _failing_after(rows, 0), _ABSENT, documents, 1)
    consumer = frames(raised.value.__traceback__, module=acquisition_module.__file__)
    assert consumer
    assert not reaches(consumer, documents)
    assert not reaches(consumer, rows[0])


def test_read_keys_compare_by_entity_identity_key_attribute_and_lock_alone() -> None:
    first, second = (target(formed(records("balance")), "Balance") for _ in range(2))
    assert first is not second
    key_attribute = AttributeIdentity(first.identity, "id")
    key = CoverageReadKey(first, key_attribute, shared_lock=True)
    alike = CoverageReadKey(second, key_attribute, shared_lock=True)
    assert key == alike
    assert len({key, alike}) == 1
    assert key != CoverageReadKey(first, key_attribute, shared_lock=False)
    assert key != CoverageReadKey(
        first, AttributeIdentity(first.identity, "acctNum"), shared_lock=True
    )
    assert key != key_attribute


def _key(request: TargetReadRequest) -> AttributeIdentity:
    ((name, _value),) = request.key.primary_key
    return AttributeIdentity(request.entity.identity, name)


# --------------------------------------------------------------------------- #
# A coverage read of several objects: each row goes to the object whose key   #
# it holds.                                                                    #
# --------------------------------------------------------------------------- #
def _shared_request() -> CoverageReadRequest:
    request = _target_request()
    terms = (CoverageTerm(1, None), CoverageTerm(2, None), CoverageTerm(3, None))
    return CoverageReadRequest(
        CoverageReadKey(request.entity, _key(request), shared_lock=False), terms
    )


def test_a_shared_reads_rows_and_documents_go_to_the_object_each_row_holds_the_key_of() -> None:
    rows = [
        (2, "Bea", Decimal("200.00"), 3),
        (1, "Ada", Decimal("100.00"), 3),
        (2, "Bea", Decimal("200.00"), 3),
        (2, "Cy", Decimal("300.00"), 3),
    ]
    documents: list[object | None] = ["raw-2a", "raw-1", "raw-2a", "raw-2b"]
    selection = _selection(_ACCOUNT, "Account")
    evidence = consume_coverage(
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
    assert consume_coverage(_shared_request(), selection, iter(()), _ABSENT, None, 0) == {}


def test_a_shared_reads_consumer_a_row_fails_in_holds_none_of_the_rows_or_documents() -> None:
    rows = [(1, "Ada", Decimal("100.00"), 3), (2, "Bea", Decimal("200.00"), 3)]
    documents: list[object | None] = ["raw-1", "raw-2"]
    selection = _selection(_ACCOUNT, "Account")
    with pytest.raises(_Unjudged) as raised:
        consume_coverage(
            _shared_request(), selection, _failing_after(rows, 2), _ABSENT, documents, 2
        )
    consumer = frames(raised.value.__traceback__, module=acquisition_module.__file__)
    assert consumer
    assert not reaches(consumer, documents)
    assert not any(reaches(consumer, row) for row in rows)
