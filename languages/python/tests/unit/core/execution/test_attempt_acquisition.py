"""The Attempt's row acquisition over a scripted port (`m-execution`): each
read in its own activity bracket, the read's resources settled however its
consumer leaves, and a target read decided by its root count once its Read has
closed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Sequence
from decimal import Decimal
from typing import Any, Final

import pytest

from parallax.conformance import models
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.class_models import MODELS
from parallax.core.base import INFINITY, DocumentValue, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow
from parallax.core.entity._model import model_of
from parallax.core.execution import _attempt as attempt_module
from parallax.core.execution._attempt import Attempt
from parallax.core.execution_lifecycle import (
    DatabaseCallStarted,
    ExecutionEvent,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadStarted,
    WriteBatchStarted,
)
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.read_delivery import StoredDataDecodingError
from parallax.core.read_delivery._row_converter import ReadRowConverter
from parallax.core.unit_work import CardinalityCorruptionError, TargetWrite
from parallax.core.unit_work.acquisition import TargetReadRequest
from parallax.core.unit_work.instructions import PreparedTargetWrite, prepare_wire_write
from parallax.core.write_plan import ObjectKey
from parallax.descriptor import domain_model_from_document
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Read,
    ReadCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
)
from tests.unit.core.execution._execution_support import ACCOUNT, account_insert, itself, scope

_META: Final = model_of(ACCOUNT)
_BALANCE: Final = MODELS["balance"]
_T0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _account(account_id: int = 1) -> MappingRow:
    return {"id": account_id, "owner": "Ada", "balance": Decimal("1.00"), "version": 3}


def _patch(*, version: int = 3) -> PreparedTargetWrite:
    return prepare_wire_write(
        TargetWrite("amend", "Account", {"id": 1, "balance": "9.00"}, if_version=version), _META
    )


def _target_request() -> TargetReadRequest:
    target = _patch().target
    return TargetReadRequest(target, ObjectKey(target.identity, (("id", 1),)), None)


def _names(events: Sequence[ExecutionEvent]) -> list[str]:
    return [type(event).__name__ for event in events]


def _read_outcomes(events: Sequence[ExecutionEvent]) -> list[object]:
    return [event.outcome for event in events if isinstance(event, ReadFinished)]


# --------------------------------------------------------------------------- #
# Target reads: the root count decides, after the Read has closed.             #
# --------------------------------------------------------------------------- #
# A Relational Document Layout target, whose target read projects the document
# its payload is judged from; a direct Column's value is established by its SQL
# type and is not judged again.
_LEDGER: Final = domain_model_from_document(
    models.read_document(models.default_models_dir() / "document-layout.yaml")
)


def _ledger(*, balance: DocumentValue = "1.00") -> MappingRow:
    return {
        "id": 1,
        "version": 3,
        "payload": PresentDocument({"label": "A", "balance": balance, "details": {"code": "x"}}),
    }


def _ledger_patch() -> PreparedTargetWrite:
    return prepare_wire_write(
        TargetWrite("amend", "Ledger", {"id": 1, "label": "Z"}, if_version=3),
        model_of(_LEDGER),
    )


def _ledger_write(rows: Sequence[MappingRow], recorder: RecordingLifecycleProvider) -> None:
    port = ScriptedAdapter(Transact(Read(rows=rows), Write()))
    scope(port, _LEDGER, provider=recorder).transact(
        lambda tx: tx.target_write(_ledger_patch()), itself, concurrency="locking"
    )


def test_several_target_rows_are_corruption_with_their_count_once_the_read_has_closed() -> None:
    # The second row's payload is invalid stored data, which judging it would
    # refuse; neither root is judged, so the count alone decides.
    recorder = RecordingLifecycleProvider()
    with raises_contextualized(CardinalityCorruptionError) as corrupt:
        _ledger_write([_ledger(), _ledger(balance=1.0)], recorder)
    assert (corrupt.value.expected, corrupt.value.actual) == (1, 2)
    (outcome,) = _read_outcomes(recorder.roots[-1].events)
    assert isinstance(outcome, ReadCompleted)


def test_a_unique_target_row_holding_invalid_stored_data_is_refused_inside_its_read() -> None:
    recorder = RecordingLifecycleProvider()
    with raises_contextualized(StoredDataDecodingError):
        _ledger_write([_ledger(balance=1.0)], recorder)
    (outcome,) = _read_outcomes(recorder.roots[-1].events)
    assert isinstance(outcome, ReadFailed)


def test_a_unique_valid_target_row_supplies_the_revision_the_caller_states() -> None:
    recorder = RecordingLifecycleProvider()
    _ledger_write([_ledger()], recorder)
    (outcome,) = _read_outcomes(recorder.roots[-1].events)
    assert isinstance(outcome, ReadCompleted)


def test_a_failing_target_read_fails_before_any_count_is_taken() -> None:
    failure = DatabaseError(category="connectionDead", native_code="08006", message="gone")
    port = ScriptedAdapter(Transact(Read(raises=failure)))
    with raises_contextualized(DatabaseError):
        scope(port).transact(lambda tx: tx.target_write(_patch()), itself, concurrency="locking")


def test_a_conversion_failure_of_a_several_root_target_read_precedes_its_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    convert = ReadRowConverter.convert_row
    converted: list[object] = []

    def failing(self: ReadRowConverter, row: Any, *arguments: Any, **keywords: Any) -> Any:
        converted.append(row)
        if len(converted) == 2:
            raise ValueError("the second row does not convert")
        return convert(self, row, *arguments, **keywords)

    monkeypatch.setattr(ReadRowConverter, "convert_row", failing)
    port = ScriptedAdapter(Transact(Read(rows=[_account(), _account()])))
    with raises_contextualized(ValueError, match="does not convert"):
        scope(port).transact(lambda tx: tx.target_write(_patch()), itself, concurrency="locking")


def test_a_target_read_is_a_read_of_its_own_that_flushes_nothing_pending() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Transact(Read(rows=[_account()]), Write(), Write()))

    def fn(tx: Attempt) -> None:
        tx.uow.buffer(account_insert())
        tx.target_write(_patch())

    scope(port, provider=recorder).transact(fn, itself, concurrency="locking")
    names = _names(recorder.roots[-1].events)
    # The pending insert executes in the pre-commit batch, after the read.
    assert names.index("ReadStarted") < names.index("WriteBatchStarted")
    assert [type(call) for call in port.calls][:2] == [BeginCall, ReadCall]
    assert isinstance(port.calls[-1], CommitCall)


# --------------------------------------------------------------------------- #
# The read's resources are settled however its consumer leaves.                #
# --------------------------------------------------------------------------- #
class _Watched:
    """Every Page row release and every member-row iterator the acquisition
    hands a consumer, as it happens."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.released = 0
        self.iterators: list[Iterator[tuple[object, ...]]] = []
        release = vars(attempt_module)["release_page_rows"]
        rows = vars(attempt_module)["publishable_member_rows"]

        def releasing(page: Any) -> None:
            self.released += 1
            release(page)

        def watching(page: Any) -> Any:
            iterator = rows(page)
            self.iterators.append(iterator)
            return iterator

        monkeypatch.setattr(attempt_module, "release_page_rows", releasing)
        monkeypatch.setattr(attempt_module, "publishable_member_rows", watching)


def _unstarted(
    request: TargetReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> int:
    del request, selection, rows, absent, documents
    return root_count


def _partial(
    request: TargetReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> int:
    del request, selection, absent, documents, root_count
    next(rows)
    return 1


class _Refused(Exception):
    pass


def _raising(
    request: TargetReadRequest,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> int:
    del request, selection, absent, documents, root_count
    next(rows)
    raise _Refused


@pytest.mark.parametrize(
    ("consumer", "answer"),
    [(_unstarted, 2), (_partial, 1), (_raising, None)],
    ids=["unstarted", "partial", "raising"],
)
def test_the_read_is_settled_however_its_consumer_leaves(
    monkeypatch: pytest.MonkeyPatch, consumer: Any, answer: int | None
) -> None:
    watched = _Watched(monkeypatch)
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Transact(Read(rows=[_account(1), _account(2)])))
    answers: list[int] = []

    def fn(tx: Attempt) -> None:
        if answer is None:
            with pytest.raises(_Refused):
                tx.uow.acquire_rows(_target_request(), consumer)
        else:
            answers.append(tx.uow.acquire_rows(_target_request(), consumer))

    scope(port, provider=recorder).transact(fn, itself, concurrency="locking")
    assert answers == ([] if answer is None else [answer])
    (iterator,) = watched.iterators
    assert next(iterator, None) is None
    assert watched.released == 1
    (outcome,) = _read_outcomes(recorder.roots[-1].events)
    assert isinstance(outcome, ReadFailed if answer is None else ReadCompleted)
    assert isinstance(port.calls[-1], CommitCall)


def test_a_coverage_read_is_a_read_call_of_the_write_batch_reaching_its_range() -> None:
    # An Optimistic caller-addressed write of a Transaction-Time object reads
    # nothing at its call; its range reads the object's coverage when the flush
    # reaches it, inside that flush's Write Batch and with no Read of its own.
    recorder = RecordingLifecycleProvider()
    stored = {
        "bal_id": 1,
        "acct_num": "A",
        "val": Decimal("5.00"),
        "in_z": _T0,
        "out_z": INFINITY,
    }
    port = ScriptedAdapter(Transact(Read(rows=[stored]), Write(), Write()))
    patch = prepare_wire_write(
        TargetWrite("amend", "Balance", {"id": 1, "value": "9.00"}, if_tx_start=_T0),
        model_of(_BALANCE),
    )
    scope(port, _BALANCE, provider=recorder).transact(
        lambda tx: tx.target_write(patch), itself, concurrency="optimistic"
    )
    events = recorder.roots[-1].events
    assert not any(isinstance(event, ReadStarted) for event in events)
    batch = next(
        index for index, event in enumerate(events) if isinstance(event, WriteBatchStarted)
    )
    first_call = next(event for event in events[batch:] if isinstance(event, DatabaseCallStarted))
    assert first_call.kind == "read"
    assert [type(call) for call in port.calls] == [
        BeginCall,
        ReadCall,
        WriteCall,
        WriteCall,
        CommitCall,
    ]
