"""The Attempt's row acquisition over a scripted port (`m-execution`): each
read in its own activity bracket, the read's resources settled however its
consumer leaves, and a target read decided by its root count once its Read has
closed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance import models
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.class_models import MODELS
from parallax.core import Attr, Bitemporal, Document, DomainModel, ValueObject, attr, inheritance
from parallax.core import predicate as predicate_algebra
from parallax.core._execution._transaction import _attempt as attempt_module
from parallax.core._execution._transaction._attempt import TxnAttempt
from parallax.core._execution._unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    CoverageTerm,
    RowConsumer,
    TargetReadRequest,
    consume_target,
)
from parallax.core._execution._unit_work.instructions import (
    PreparedPredicateInstruction,
    PreparedTargetInstruction,
    prepare_wire_write,
)
from parallax.core.base import INFINITY, SQL_NULL, DocumentValue, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow, OrderedWriteResultComplete
from parallax.core.document_codec import _document as document_module
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle import (
    DatabaseCallStarted,
    ExecutionEvent,
    FlushStarted,
    ReadCompleted,
    ReadFailed,
    ReadFinished,
    ReadStarted,
)
from parallax.core.inheritance import EntityMemberSelection
from parallax.core.metamodel import (
    AttributeIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.read_delivery import StoredDataDecodingError
from parallax.core.read_delivery._row_converter import ReadRowConverter
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import (
    CardinalityCorruptionError,
    OptimisticLockConflictError,
    PredicateSelection,
    PredicateWriteInstruction,
    TargetWriteInstruction,
    WriteAssignment,
)
from parallax.core.write_plan import ObjectKey
from parallax.core.write_plan.steps import MilestoneTarget
from parallax.descriptor import domain_model_from_document
from tests._support.adoption import raises_contextualized
from tests._support.db_port import (
    BeginCall,
    CommitCall,
    Ordered,
    OrderedCall,
    Read,
    ReadCall,
    RollbackCall,
    ScriptedAdapter,
    Transact,
    Write,
    WriteCall,
    inserted_rows,
)
from tests.unit import _family_predecessor_support as family
from tests.unit.core._execution import _shared_coverage_support as shared
from tests.unit.core._execution._execution_support import ACCOUNT, account_insert, itself, scope
from tests.unit.core._execution._reach_support import frames, reaches

_META: Final = model_of(ACCOUNT)
_BALANCE: Final = MODELS["balance"]
_T0: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


def _account(account_id: int = 1) -> MappingRow:
    return {"id": account_id, "owner": "Ada", "balance": Decimal("1.00"), "version": 3}


def _patch(*, version: int = 3) -> PreparedTargetInstruction:
    return prepare_wire_write(
        TargetWriteInstruction(
            "amend", "Account", {"id": 1, "balance": "9.00"}, if_version=version
        ),
        _META,
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


def _ledger_patch() -> PreparedTargetInstruction:
    return prepare_wire_write(
        TargetWriteInstruction("amend", "Ledger", {"id": 1, "label": "Z"}, if_version=3),
        model_of(_LEDGER),
    )


def _ledger_write(rows: Sequence[MappingRow], recorder: RecordingLifecycleProvider) -> None:
    port = ScriptedAdapter(Transact(Read(rows=rows), Write()))
    scope(port, _LEDGER, provider=recorder).transact(
        lambda tx: tx.uow.buffer_target(_ledger_patch()), itself, concurrency="locking"
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
        scope(port).transact(
            lambda tx: tx.uow.buffer_target(_patch()), itself, concurrency="locking"
        )


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
        scope(port).transact(
            lambda tx: tx.uow.buffer_target(_patch()), itself, concurrency="locking"
        )


def test_a_target_read_is_a_read_of_its_own_that_flushes_nothing_pending() -> None:
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Transact(Read(rows=[_account()]), Write(), Write()))

    def fn(tx: TxnAttempt) -> None:
        tx.uow.buffer_insert(account_insert(), insertion_advice=None)
        tx.uow.buffer_target(_patch())

    scope(port, provider=recorder).transact(fn, itself, concurrency="locking")
    names = _names(recorder.roots[-1].events)
    # The pending insert executes in the pre-commit flush, after the read.
    assert names.index("ReadStarted") < names.index("FlushStarted")
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

    def fn(tx: TxnAttempt) -> None:
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


def _ledger_request() -> TargetReadRequest:
    target = _ledger_patch().target
    return TargetReadRequest(target, ObjectKey(target.identity, (("id", 1),)), None)


def _halting(
    after: int, handed: list[Sequence[object | None] | None]
) -> RowConsumer[TargetReadRequest, int]:
    """A consumer recording the raw documents it is handed, then raising
    after ``after`` rows."""

    def consume(
        request: TargetReadRequest,
        selection: EntityMemberSelection,
        rows: Iterator[tuple[object, ...]],
        absent: object,
        documents: Sequence[object | None] | None,
        root_count: int,
    ) -> int:
        del request, selection, absent, root_count
        handed.append(documents)
        for _ in range(after):
            next(rows)
        raise _Refused

    return consume


@pytest.mark.parametrize("after", [0, 1], ids=["before-the-rows", "part-way"])
def test_a_failed_consumer_leaves_the_reader_holding_none_of_the_reads_documents(
    after: int,
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ledger(), _ledger()])))
    failures: list[_Refused] = []
    handed: list[Sequence[object | None] | None] = []

    def fn(tx: TxnAttempt) -> None:
        try:
            tx.uow.acquire_rows(_ledger_request(), _halting(after, handed))
        except _Refused as failure:
            failures.append(failure)

    scope(port, _LEDGER).transact(fn, itself, concurrency="locking")
    (failure,) = failures
    (documents,) = handed
    assert documents is not None and len(documents) == 2
    # The failure keeps its traceback, through the reader's own frames.
    reader = frames(failure.__traceback__, module=attempt_module.__file__)
    assert reader
    assert not reaches(reader, documents)


def test_what_a_consumer_answers_keeps_the_document_it_adopted_once_the_reader_let_go() -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_ledger()])))
    answers: list[tuple[int, tuple[object, ...] | None, object | None]] = []
    scope(port, _LEDGER).transact(
        lambda tx: answers.append(tx.uow.acquire_rows(_ledger_request(), consume_target)),
        itself,
        concurrency="locking",
    )
    ((count, row, document),) = answers
    assert count == 1
    assert row is not None
    assert document == {"label": "A", "balance": "1.00", "details": {"code": "x"}}


def test_a_coverage_read_is_a_read_call_of_the_flush_reaching_its_range() -> None:
    # An Optimistic target write of a Transaction-Time object reads
    # nothing at its call; its range reads the object's coverage when the flush
    # reaches it, inside that flush's activity and with no Read of its own.
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
        TargetWriteInstruction("amend", "Balance", {"id": 1, "value": "9.00"}, if_tx_start=_T0),
        model_of(_BALANCE),
    )
    scope(port, _BALANCE, provider=recorder).transact(
        lambda tx: tx.uow.buffer_target(patch), itself, concurrency="optimistic"
    )
    events = recorder.roots[-1].events
    assert not any(isinstance(event, ReadStarted) for event in events)
    flush = next(index for index, event in enumerate(events) if isinstance(event, FlushStarted))
    first_call = next(event for event in events[flush:] if isinstance(event, DatabaseCallStarted))
    assert first_call.kind == "read"
    assert [type(call) for call in port.calls] == [
        BeginCall,
        ReadCall,
        WriteCall,
        WriteCall,
        CommitCall,
    ]


def test_each_deferred_range_reads_its_coverage_only_once_the_write_before_it_ran() -> None:
    # Two Optimistic target writes are two deferred settled writes of one flush:
    # each reads its coverage at its own turn, so the second settled write's read follows
    # the first settled write's statements rather than being prepared alongside them.
    recorder = RecordingLifecycleProvider()

    def stored(key: int) -> MappingRow:
        return {
            "bal_id": key,
            "acct_num": "A",
            "val": Decimal("5.00"),
            "in_z": _T0,
            "out_z": INFINITY,
        }

    port = ScriptedAdapter(
        Transact(Read(rows=[stored(1)]), Write(), Write(), Read(rows=[stored(2)]), Write(), Write())
    )
    patches = [
        prepare_wire_write(
            TargetWriteInstruction(
                "amend", "Balance", {"id": key, "value": "9.00"}, if_tx_start=_T0
            ),
            model_of(_BALANCE),
        )
        for key in (1, 2)
    ]

    def fn(tx: TxnAttempt) -> None:
        for patch in patches:
            tx.uow.buffer_target(patch)

    scope(port, _BALANCE, provider=recorder).transact(fn, itself, concurrency="optimistic")
    assert [type(call) for call in port.calls] == [
        BeginCall,
        ReadCall,
        WriteCall,
        WriteCall,
        ReadCall,
        WriteCall,
        WriteCall,
        CommitCall,
    ]
    events = recorder.roots[-1].events
    assert sum(isinstance(event, FlushStarted) for event in events) == 1


# --------------------------------------------------------------------------- #
# A retained target row: its Attributes judged by its read, its occurrences    #
# by its completion, exactly as a read of the same stored row judges them.     #
# --------------------------------------------------------------------------- #
class HullMark(ValueObject):
    title: Attr[str]


class HullSpec(ValueObject):
    title: Attr[str]
    marks: Attr[tuple[HullMark, ...]]
    labels: Attr[tuple[str, ...]]


class ColumnsHull(Bitemporal, table="hull_columns", namespace="parallax.execution"):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]]
    spec: Attr[HullSpec | None]
    keel: Attr[HullMark]
    marks: Attr[tuple[HullMark, ...]]


class DocumentHull(
    Bitemporal, table="hull_document", namespace="parallax.execution", layout=Document()
):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[int]
    tags: Attr[tuple[str, ...]]
    spec: Attr[HullSpec | None]
    keel: Attr[HullMark]
    marks: Attr[tuple[HullMark, ...]]


_HULLS: Final = DomainModel(ColumnsHull, DocumentHull)
_JAN: Final = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_MAR: Final = dt.datetime(2024, 3, 1, tzinfo=dt.UTC)
_SQL_NULL_OCCURRENCE: Final = object()
_VALID: Final[dict[str, object]] = {
    "tags": ["t", "t"],
    "spec": {"title": "s", "marks": [{"title": "n"}], "labels": ["l"]},
    "keel": {"title": "k"},
    "marks": [{"title": "m"}],
}


def _hull_row(entity: type[Any], occurrences: Mapping[str, object]) -> MappingRow:
    axes: dict[str, object] = {"from_z": _JAN, "thru_z": INFINITY, "in_z": _T0, "out_z": INFINITY}
    if entity is DocumentHull:
        document: dict[str, DocumentValue] = {"amount": 100}
        for name, value in occurrences.items():
            if value is not _SQL_NULL_OCCURRENCE:
                document[name] = cast("DocumentValue", value)
        return {"id": 1, **axes, "payload": PresentDocument(document)}
    row: dict[str, object] = {"id": 1, "amount": 100, **axes}
    for name, value in occurrences.items():
        row[name] = (
            SQL_NULL
            if value is _SQL_NULL_OCCURRENCE
            else PresentDocument(cast("DocumentValue", value))
        )
    return row


_STORED: Final[dict[str, Mapping[str, object]]] = {
    "valid": _VALID,
    "nullable-sql-null": {**_VALID, "spec": _SQL_NULL_OCCURRENCE},
    "nullable-json-null": {**_VALID, "spec": None},
    "required-sql-null": {**_VALID, "keel": _SQL_NULL_OCCURRENCE},
    "required-json-null": {**_VALID, "keel": None},
    "nested-leaf": {**_VALID, "spec": {"title": 7, "marks": []}},
    "nested-many-kind": {**_VALID, "spec": {"title": "s", "marks": {"title": "n"}}},
    "many-element-leaf": {**_VALID, "marks": [{"title": "m"}, {"title": 2}]},
    "one-kind": {**_VALID, "keel": ["k"]},
    "unknown-keys": {**_VALID, "spec": {"title": "s", "marks": [], "extra": 1}},
    "collection-sql-null": {**_VALID, "tags": _SQL_NULL_OCCURRENCE},
    "collection-json-null": {**_VALID, "tags": None},
    "nested-collection-element": {**_VALID, "spec": {"title": "s", "marks": [], "labels": [3]}},
}


def _hull_keys(entity: type[Any]) -> tuple[Any, ObjectKey]:
    metadata = entity_by_name(model_of(_HULLS), f"parallax.execution.{entity.__name__}")
    assert metadata is not None
    return metadata, ObjectKey(metadata.identity, (("id", 1),))


def _judged(acquire: Any) -> object:
    """The member rows an acquisition hands its consumer, or the refusal it raised."""
    try:
        return acquire()
    except StoredDataDecodingError as refused:
        return (refused.message, refused.entity, refused.member)


def _member_rows(
    request: object,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> list[tuple[object, ...]]:
    del request, selection, absent, documents, root_count
    return list(rows)


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
@pytest.mark.parametrize("stored", list(_STORED), ids=list(_STORED))
def test_a_completed_retained_row_is_judged_as_a_coverage_read_judges_it(
    entity: type[Any], stored: str
) -> None:
    row = _hull_row(entity, _STORED[stored])
    port = ScriptedAdapter(Transact(Read(rows=[row]), Read(rows=[row])))
    metadata, key = _hull_keys(entity)
    key_attribute = AttributeIdentity(metadata.identity, "id")
    seen: list[object] = []

    def fn(tx: TxnAttempt) -> None:
        coverage = CoverageReadRequest(
            metadata,
            key_attribute,
            (CoverageTerm(1, (TimeInterval(_JAN, INFINITY),)),),
            locking=True,
        )
        seen.append(_judged(lambda: tx.uow.acquire_rows(coverage, _member_rows)))
        count, retained, document = tx.uow.acquire_rows(
            TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
        )
        assert count == 1 and retained is not None
        completion = CompletionRequest(
            metadata, key_attribute, (retained,), None if document is None else (document,)
        )
        seen.append(_judged(lambda: tx.uow.acquire_rows(completion, _member_rows)))

    scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    ordinary, completed = seen
    assert completed == ordinary


def test_a_non_object_structured_column_is_refused_alike_by_a_retaining_read() -> None:
    # Every member located in a non-object document is missing: the required
    # Attribute refuses the row at the read, as it refuses an ordinary read.
    row = {**_hull_row(DocumentHull, _VALID), "payload": PresentDocument(["not", "an", "object"])}
    port = ScriptedAdapter(Transact(Read(rows=[row]), Read(rows=[row])))
    metadata, key = _hull_keys(DocumentHull)
    key_attribute = AttributeIdentity(metadata.identity, "id")
    seen: list[object] = []

    def fn(tx: TxnAttempt) -> None:
        coverage = CoverageReadRequest(
            metadata,
            key_attribute,
            (CoverageTerm(1, (TimeInterval(_JAN, INFINITY),)),),
            locking=True,
        )
        seen.append(_judged(lambda: tx.uow.acquire_rows(coverage, _member_rows)))
        seen.append(
            _judged(
                lambda: tx.uow.acquire_rows(
                    TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
                )
            )
        )

    scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    ordinary, retaining = seen
    assert retaining == ordinary
    assert ordinary == (
        "parallax.execution.DocumentHull holds invalid stored data (stored-data-attribute-null)",
        metadata.identity,
        AttributeIdentity(metadata.identity, "amount"),
    )


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
def test_several_target_rows_with_invalid_collections_are_corruption_before_judgment(
    entity: type[Any],
) -> None:
    row = _hull_row(entity, {**_VALID, "tags": ["t", 2]})
    metadata, key = _hull_keys(entity)
    port = ScriptedAdapter(Transact(Read(rows=[row, row])))
    counts: list[int] = []

    def fn(tx: TxnAttempt) -> None:
        count, retained, _document = tx.uow.acquire_rows(
            TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
        )
        assert retained is None
        counts.append(count)

    scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    assert counts == [2]


class _Stopped(Exception):
    pass


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
def test_a_write_reusing_a_pending_participation_reads_and_judges_nothing_again(
    entity: type[Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    interpreted: list[str] = []
    interpret = vars(document_module)["_interpreted_scalar_many"]

    def counting(member: Any, raw: object, path: Any) -> Any:
        interpreted.append(member.name)
        return interpret(member, raw, path)

    monkeypatch.setattr(document_module, "_interpreted_scalar_many", counting)
    port = ScriptedAdapter(Transact(Read(rows=[_hull_row(entity, _VALID)])))
    metadata, _key = _hull_keys(entity)

    def amend(tags: list[str]) -> PreparedTargetInstruction:
        return prepare_wire_write(
            TargetWriteInstruction(
                "amend",
                metadata.identity.canonical,
                {"id": 1, "tags": tags},
                if_tx_start=_T0,
                valid_from=_MAR,
            ),
            model_of(_HULLS),
        )

    def fn(tx: TxnAttempt) -> None:
        tx.uow.buffer_target(amend(["a"]))
        assert interpreted == ["tags"]
        tx.uow.buffer_target(amend(["b", "b"]))
        assert interpreted == ["tags"]
        assert [type(call) for call in port.calls] == [BeginCall, ReadCall]
        raise _Stopped

    with raises_contextualized(_Stopped):
        scope(port, _HULLS).transact(fn, itself, concurrency="locking")


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
def test_an_optimistic_target_reads_no_collection_until_its_flush_covers_it(
    entity: type[Any],
) -> None:
    # Optimistic admission reads nothing, so an invalid collection is first met
    # by the coverage read the flush makes for the write's range.
    recorder = RecordingLifecycleProvider()
    port = ScriptedAdapter(Transact(Read(rows=[_hull_row(entity, {**_VALID, "tags": [1]})])))
    metadata, _key = _hull_keys(entity)
    called: list[str] = []

    def fn(tx: TxnAttempt) -> None:
        tx.uow.buffer_target(
            prepare_wire_write(
                TargetWriteInstruction(
                    "amend",
                    metadata.identity.canonical,
                    {"id": 1, "amount": 5},
                    if_tx_start=_T0,
                    valid_from=_MAR,
                ),
                model_of(_HULLS),
            )
        )
        assert [type(call) for call in port.calls] == [BeginCall]
        called.append("returned")

    with raises_contextualized(StoredDataDecodingError) as refused:
        scope(port, _HULLS, provider=recorder).transact(fn, itself, concurrency="optimistic")
    assert called == ["returned"]
    assert refused.value.member == AttributeIdentity(metadata.identity, "tags")


_INVALID_COLLECTIONS: Final[dict[str, object]] = {
    "kind": {"t": 1},
    "elements": ["t", 1, "u", False],
}


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
@pytest.mark.parametrize("stored", list(_INVALID_COLLECTIONS), ids=list(_INVALID_COLLECTIONS))
def test_a_retaining_read_judges_a_top_level_collection_as_a_coverage_read_judges_it(
    entity: type[Any], stored: str
) -> None:
    # A scalar collection is an Attribute wherever it is stored, so the retaining
    # read judges it with the prefix rather than leaving it to completion.
    row = _hull_row(entity, {**_VALID, "tags": _INVALID_COLLECTIONS[stored]})
    port = ScriptedAdapter(Transact(Read(rows=[row]), Read(rows=[row])))
    metadata, key = _hull_keys(entity)
    key_attribute = AttributeIdentity(metadata.identity, "id")
    seen: list[object] = []

    def fn(tx: TxnAttempt) -> None:
        coverage = CoverageReadRequest(
            metadata,
            key_attribute,
            (CoverageTerm(1, (TimeInterval(_JAN, INFINITY),)),),
            locking=True,
        )
        seen.append(_judged(lambda: tx.uow.acquire_rows(coverage, _member_rows)))
        seen.append(
            _judged(
                lambda: tx.uow.acquire_rows(
                    TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
                )
            )
        )

    scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    ordinary, retaining = seen
    invalid = f"{metadata.identity.canonical} holds invalid stored data"
    assert retaining == ordinary
    assert ordinary == (
        f"{invalid} (stored-data-leaf-undecodable)",
        metadata.identity,
        AttributeIdentity(metadata.identity, "tags"),
    )


_INVALID_SPECS: Final[dict[str, tuple[dict[str, object], str]]] = {
    "leaf": ({"title": 7, "marks": []}, "title"),
    "nested-collection": ({"title": "s", "marks": [], "labels": ["l", 3]}, "labels"),
}


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
@pytest.mark.parametrize("invalid", list(_INVALID_SPECS), ids=list(_INVALID_SPECS))
def test_a_retained_rows_invalid_occurrence_fails_at_its_flush_not_its_call(
    entity: type[Any], invalid: str
) -> None:
    # The occurrence is judged when the flush completes the row it reuses, after
    # the call has returned and inside the flush, with no read of its own;
    # a scalar collection inside it is judged with it.
    recorder = RecordingLifecycleProvider()
    spec, failing = _INVALID_SPECS[invalid]
    row = _hull_row(entity, {**_VALID, "spec": spec})
    port = ScriptedAdapter(Transact(Read(rows=[row])))
    metadata, _key = _hull_keys(entity)
    called: list[str] = []

    def fn(tx: TxnAttempt) -> None:
        tx.uow.buffer_target(
            prepare_wire_write(
                TargetWriteInstruction(
                    "amend",
                    metadata.identity.canonical,
                    {"id": 1, "amount": 5},
                    if_tx_start=_T0,
                    valid_from=_MAR,
                ),
                model_of(_HULLS),
            )
        )
        called.append("returned")

    with raises_contextualized(StoredDataDecodingError) as refused:
        scope(port, _HULLS, provider=recorder).transact(fn, itself, concurrency="locking")
    assert called == ["returned"]
    assert refused.value.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(metadata.identity, ("spec",)), failing
    )
    events = recorder.roots[-1].events
    (read,) = [event for event in events if isinstance(event, ReadStarted)]
    flush = next(index for index, event in enumerate(events) if isinstance(event, FlushStarted))
    assert events.index(read) < flush
    assert not any(isinstance(event, DatabaseCallStarted) for event in events[flush:])


def test_a_completion_reads_nothing_and_opens_no_activity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    interpreted: list[str] = []
    interpret = vars(document_module)["_interpreted_scalar_many"]

    def counting(member: Any, raw: object, path: Any) -> Any:
        interpreted.append(member.name)
        return interpret(member, raw, path)

    monkeypatch.setattr(document_module, "_interpreted_scalar_many", counting)
    recorder = RecordingLifecycleProvider()
    row = _hull_row(DocumentHull, _VALID)
    port = ScriptedAdapter(Transact(Read(rows=[row])))
    metadata, key = _hull_keys(DocumentHull)
    key_attribute = AttributeIdentity(metadata.identity, "id")

    def fn(tx: TxnAttempt) -> None:
        _count, retained, document = tx.uow.acquire_rows(
            TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
        )
        assert retained is not None
        # The retaining read judged the top-level collection with the prefix.
        assert interpreted == ["tags"]
        completion = CompletionRequest(metadata, key_attribute, (retained,), (document,))
        (completed,) = tx.uow.acquire_rows(completion, _member_rows)
        # Completion decodes only the collection inside the pending occurrence.
        assert interpreted == ["tags", "labels"]
        assert completed[:3] == (1, 100, ("t", "t"))
        assert completed[-3:] == (("s", ("l",), (("n",),)), ("k",), (("m",),))
        assert [type(call) for call in port.calls] == [BeginCall, ReadCall]

    scope(port, _HULLS, provider=recorder).transact(fn, itself, concurrency="locking")
    names = _names(recorder.roots[-1].events)
    assert names.count("ReadStarted") == 1
    assert names.count("DatabaseCallStarted") == 1


@pytest.mark.parametrize("entity", [ColumnsHull, DocumentHull], ids=["columns", "document"])
@pytest.mark.parametrize("attribute", ["scalar", "collection"])
def test_a_retaining_reads_invalid_attribute_is_refused_at_its_call(
    entity: type[Any], attribute: str
) -> None:
    # An Attribute is judged as the narrow read judged it, before the stated
    # revision is compared; the occurrences beside it are left to the flush. A
    # scalar collection is such an Attribute under either layout.
    row = _hull_row(entity, {**_VALID, "spec": {"title": 7, "marks": []}})
    if attribute == "collection":
        row = _hull_row(entity, {**_VALID, "tags": ["t", 2], "spec": {"title": 7, "marks": []}})
    elif entity is DocumentHull:
        payload = row["payload"]
        assert isinstance(payload, PresentDocument)
        document = cast("dict[str, DocumentValue]", payload.document)
        row = {**row, "payload": PresentDocument({**document, "amount": None})}
    else:
        # A native Column is trusted as the provider returned it; a temporal
        # end is host-checked.
        row = {**row, "thru_z": None}
    port = ScriptedAdapter(Transact(Read(rows=[row])))
    metadata, _key = _hull_keys(entity)
    refused: list[StoredDataDecodingError] = []

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(StoredDataDecodingError) as caught:
            tx.uow.buffer_target(
                prepare_wire_write(
                    TargetWriteInstruction(
                        "amend",
                        metadata.identity.canonical,
                        {"id": 1, "amount": 5},
                        if_tx_start=dt.datetime(1999, 1, 1, tzinfo=dt.UTC),
                        valid_from=_MAR,
                    ),
                    model_of(_HULLS),
                )
            )
        refused.append(caught.value)

    scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    (failure,) = refused
    member = (
        "tags" if attribute == "collection" else "amount" if entity is DocumentHull else "validEnd"
    )
    assert failure.member == AttributeIdentity(metadata.identity, member)


# --------------------------------------------------------------------------- #
# An acquisition span's shared reads: the failure encountered first           #
# propagates (`m-unit-work` *Shared coverage acquisition*).                    #
# --------------------------------------------------------------------------- #
def _hull_target(metadata: Any, key: int) -> PreparedTargetInstruction:
    return prepare_wire_write(
        TargetWriteInstruction(
            "amend",
            metadata.identity.canonical,
            {"id": key, "amount": 5},
            if_tx_start=_T0,
            valid_from=_MAR,
        ),
        model_of(_HULLS),
    )


def test_a_later_writes_retained_row_fails_its_completion_before_the_span_binds_any_write() -> None:
    # Both Locking target writes' retained rows cover their windows, so the
    # first is ready at once; the second's invalid occurrence still fails
    # first, as the span completes every retained row before binding.
    spec, _failing = _INVALID_SPECS["leaf"]
    valid = _hull_row(ColumnsHull, _VALID)
    invalid = {**_hull_row(ColumnsHull, {**_VALID, "spec": spec}), "id": 2}
    port = ScriptedAdapter(Transact(Read(rows=[valid]), Read(rows=[invalid])))
    metadata, _key = _hull_keys(ColumnsHull)

    def fn(tx: TxnAttempt) -> None:
        tx.uow.buffer_target(_hull_target(metadata, 1))
        tx.uow.buffer_target(_hull_target(metadata, 2))

    with raises_contextualized(StoredDataDecodingError):
        scope(port, _HULLS).transact(fn, itself, concurrency="locking")
    # No coverage read, no write of either object, and no retry.
    assert [type(call) for call in port.calls] == [BeginCall, ReadCall, ReadCall, RollbackCall]


def _odd_rows(
    entity: type[Bitemporal], key: int, parts: int, *, first: int = 0
) -> list[MappingRow]:
    """``frag(key, parts)``'s odd rectangles from ``R_{2 first + 1}`` on, as
    the database answers the reads of their parts."""
    rows = shared.frag_rows(entity, key, parts)
    return [shared.physical_row(entity, rows[2 * pair + 1]) for pair in range(first, parts)]


def _correct(*objects: tuple[type[Bitemporal], int, int]) -> Callable[[TxnAttempt], None]:
    def fn(tx: TxnAttempt) -> None:
        for entity, key, parts in objects:
            for write in shared.frag(entity, key, parts):
                tx.uow.buffer(write)

    return fn


def _written_keys(port: ScriptedAdapter) -> set[object]:
    """The key of every object a write the port received names."""
    keys: set[object] = set()
    for call in port.calls:
        if isinstance(call, WriteCall):
            if call.sql.startswith("insert"):
                keys.update(row[0] for row in inserted_rows(call))
            else:
                keys.add(call.binds[1])
    return keys


def _flush_calls(port: ScriptedAdapter) -> list[type[object]]:
    return [type(call) for call in port.calls if not isinstance(call, BeginCall | RollbackCall)]


def test_an_invalid_later_row_of_a_shared_read_fails_before_an_earlier_write_binds() -> None:
    first = shared.physical_row(shared.ShareDoc, shared.frag_rows(shared.ShareDoc, 1, 1)[1])
    second = shared.physical_row(shared.ShareDoc, shared.frag_rows(shared.ShareDoc, 2, 1)[1])
    second["payload"] = PresentDocument({"amount": "x", "label": "k2"})
    # The scripted write would make the first write's close a conflict.
    port = ScriptedAdapter(Transact(Read(rows=[first, second]), Write(affected=0)))
    with raises_contextualized(StoredDataDecodingError):
        scope(port, shared.DOMAIN).transact(
            _correct((shared.ShareDoc, 1, 1), (shared.ShareDoc, 2, 1)),
            itself,
            concurrency="optimistic",
        )
    # Not retry-eligible: one attempt, whose shared read failed before the
    # first write executed anything.
    assert _flush_calls(port) == [ReadCall]
    assert sum(isinstance(call, BeginCall) for call in port.calls) == 1


def test_a_ready_writes_failure_precedes_the_read_its_successor_waits_for() -> None:
    deadlock = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port = ScriptedAdapter(
        Transact(
            Read(rows=[*_odd_rows(shared.ShareCols, 1, 1), *_odd_rows(shared.ShareCols, 2, 63)]),
            Write(affected=0),
            Read(raises=deadlock),
        )
    )
    with raises_contextualized(OptimisticLockConflictError):
        scope(port, shared.DOMAIN).transact(
            _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 64)),
            itself,
            concurrency="optimistic",
            max_retries=0,
        )
    # The first write's close conflicted before the read its successor waits
    # for; no write of the successor ran.
    assert _flush_calls(port) == [ReadCall, WriteCall]
    assert _written_keys(port) == {1}


def test_a_later_reads_failure_leaves_the_writes_completed_before_it() -> None:
    deadlock = DatabaseError(category="deadlock", native_code="40P01", message="deadlock detected")
    port = ScriptedAdapter(
        Transact(
            Read(rows=[*_odd_rows(shared.ShareCols, 1, 1), *_odd_rows(shared.ShareCols, 2, 63)]),
            Write(times=3),
            Read(raises=deadlock),
        )
    )
    with raises_contextualized(DatabaseError) as raised:
        scope(port, shared.DOMAIN).transact(
            _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 64), (shared.ShareCols, 3, 1)),
            itself,
            concurrency="optimistic",
            max_retries=0,
        )
    assert raised.value.category == "deadlock"
    assert _flush_calls(port) == [ReadCall, WriteCall, WriteCall, WriteCall, ReadCall]
    assert _written_keys(port) == {1}


def _both_ready() -> list[MappingRow]:
    """The rows the one shared read of ``frag(1, 1)`` and ``frag(2, 1)``
    returns, after which both writes are ready and run as one group."""
    return [*_odd_rows(shared.ShareCols, 1, 1), *_odd_rows(shared.ShareCols, 2, 1)]


def test_a_ready_groups_closes_share_one_invocation_ahead_of_one_insert_of_every_opening() -> None:
    port = ScriptedAdapter(
        Transact(
            Read(rows=_both_ready()),
            Ordered(OrderedWriteResultComplete((1, 1, 1, 1))),
            Write(affected=4),
        ),
        ordered=True,
    )
    scope(port, shared.DOMAIN).transact(
        _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 1)),
        itself,
        concurrency="optimistic",
    )
    assert _flush_calls(port) == [ReadCall, OrderedCall, WriteCall, CommitCall]
    _read, ordered_call, insert, _commit = [
        call for call in port.calls if not isinstance(call, BeginCall)
    ]
    assert isinstance(ordered_call, OrderedCall)
    assert isinstance(insert, WriteCall)
    # Each object's two closes, in member order, then each object's merged
    # amendment and tail, in member order.
    assert [close.binds[1] for close in ordered_call.writes] == [1, 1, 2, 2]
    assert [row[0] for row in inserted_rows(insert)] == [1, 1, 2, 2]


def test_a_later_writes_shortfall_in_a_ready_group_precedes_an_earlier_writes_insert() -> None:
    port = ScriptedAdapter(
        Transact(Read(rows=_both_ready()), Write(times=3), Write(affected=0)),
    )
    with raises_contextualized(OptimisticLockConflictError) as raised:
        scope(port, shared.DOMAIN).transact(
            _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 1)),
            itself,
            concurrency="optimistic",
            max_retries=0,
        )
    target = raised.value.target
    assert isinstance(target, MilestoneTarget)
    assert target.key_values == (2,)
    # Run alone, object 1's insert would have run before object 2's closes.
    assert _flush_calls(port) == [ReadCall, *[WriteCall] * 4]
    assert not any(
        isinstance(call, WriteCall) and call.sql.startswith("insert") for call in port.calls
    )
    assert _written_keys(port) == {1, 2}


def test_a_ready_groups_failing_insert_reports_its_statement_error_alone() -> None:
    failure = DatabaseError(category="uniqueViolation", native_code="23505", message="duplicate")
    port = ScriptedAdapter(
        Transact(Read(rows=_both_ready()), Write(times=4), Write(raises=failure)),
    )
    with raises_contextualized(DatabaseError) as raised:
        scope(port, shared.DOMAIN).transact(
            _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 1)),
            itself,
            concurrency="optimistic",
            max_retries=0,
        )
    assert raised.value is failure
    # The grouped insert of both objects' openings is the last call: nothing
    # is replayed, read, or attributed to one object after it.
    assert _flush_calls(port) == [ReadCall, *[WriteCall] * 5]
    insert = port.calls[-2]
    assert isinstance(insert, WriteCall)
    assert [row[0] for row in inserted_rows(insert)] == [1, 1, 2, 2]


def _tag_predicate() -> PreparedPredicateInstruction:
    tag = shared.ShareTag.identity.canonical
    prepared = prepare_wire_write(
        PredicateWriteInstruction(
            "amend",
            PredicateSelection(
                tag,
                predicate_algebra.Comparison("eq", predicate_algebra.FieldSubject(f"{tag}.id"), 1),
            ),
            assignments=(WriteAssignment(f"{tag}.label", "q"),),
        ),
        model_of(shared.DOMAIN),
    )
    assert isinstance(prepared, PreparedPredicateInstruction)
    return prepared


@pytest.mark.parametrize("trigger", ["read_dependency", "predicate_write", "pre_commit"])
def test_a_shared_coverage_read_is_one_read_call_of_the_flush_reaching_its_span(
    trigger: str,
) -> None:
    recorder = RecordingLifecycleProvider()
    stored = [*_odd_rows(shared.ShareCols, 1, 1), *_odd_rows(shared.ShareCols, 2, 1)]
    predicate = (Write(),) if trigger == "predicate_write" else ()
    # Both objects are ready after the one read and execute as one group: each
    # closes its two rectangles alone, and their four successors share one
    # insert.
    port = ScriptedAdapter(Transact(Read(rows=stored), Write(times=5), *predicate))

    def fn(tx: TxnAttempt) -> None:
        _correct((shared.ShareCols, 1, 1), (shared.ShareCols, 2, 1))(tx)
        if trigger == "read_dependency":
            tx.uow.read(lambda: None)
        elif trigger == "predicate_write":
            tx.uow.execute_predicate(_tag_predicate())

    scope(port, shared.DOMAIN, provider=recorder).transact(fn, itself, concurrency="optimistic")
    events = recorder.roots[-1].events
    (flush,) = [event for event in events if isinstance(event, FlushStarted)]
    assert flush.trigger == trigger
    calls = [event.kind for event in events if isinstance(event, DatabaseCallStarted)]
    # One read names both objects' parts, ahead of their group's writes.
    assert calls == ["read", *(["write"] * (5 + len(predicate)))]
    (read,) = [call for call in port.calls if isinstance(call, ReadCall)]
    assert read.sql.count("t0.id = ") == 2


# --------------------------------------------------------------------------- #
# A family member's predecessor reads: every Value Object and, under           #
# Relational Document Layout, the raw Structured Column, whatever the strategy. #
# --------------------------------------------------------------------------- #
_FAMILY_PREDECESSORS: Final[Mapping[family.Member, Mapping[str, DocumentValue]]] = {
    "Holding": {
        "origin": {"city": "Rome", "zone": None},
        "name": "n",
        "home": {"city": "Oslo", "zone": "a"},
        "extra": {"city": "Bern", "zone": None},
    },
    "Vault": {"origin": {"city": "Rome", "zone": None}, "deposit": {"city": "Lima", "zone": "c"}},
    "Bare": {},
}
_AXES_COMPLETED: Final = (1, _JAN, INFINITY, _T0, INFINITY)
_COMPLETED_MEMBERS: Final[Mapping[family.Member, tuple[object, ...]]] = {
    "Holding": (*_AXES_COMPLETED, "n", ("Rome", None), ("Oslo", "a"), ("Bern", None)),
    "Vault": (*_AXES_COMPLETED, ("Rome", None), ("Lima", "c")),
    "Bare": _AXES_COMPLETED,
}
"""Each member's complete row: its key and axes, its Attributes, then its
occurrences, in member-selection order."""


def _family_member(
    strategy: family.Strategy, layout: family.Layout, member: family.Member
) -> tuple[Any, ObjectKey, AttributeIdentity]:
    metadata = family.member_metadata(strategy, layout, member)
    view = inheritance.view(model_of(family.MODEL)).entity(metadata.identity)
    assert view is not None
    return metadata, ObjectKey(metadata.identity, (("id", 1),)), view.primary_key.identity


def _family_row(
    strategy: family.Strategy,
    layout: family.Layout,
    member: family.Member,
    values: Mapping[str, DocumentValue] | None = None,
) -> MappingRow:
    return family.stored_row(
        strategy,
        layout,
        member,
        _FAMILY_PREDECESSORS[member] if values is None else values,
        valid=(_JAN, INFINITY),
        tx_start=_T0,
    )


def _raw_document(layout: family.Layout, member: family.Member) -> object | None:
    """The Structured Column a predecessor read retains beside its row, or
    absence under ``Columns``, where there is none."""
    if layout == "columns":
        return None
    return {**_FAMILY_PREDECESSORS[member], family.UNKNOWN_KEY: "kept"}


def _rows_and_documents(
    request: object,
    selection: EntityMemberSelection,
    rows: Iterator[tuple[object, ...]],
    absent: object,
    documents: Sequence[object | None] | None,
    root_count: int,
) -> tuple[list[tuple[object, ...]], list[object | None] | None]:
    del request, selection, absent, root_count
    return list(rows), None if documents is None else list(documents)


@family.FAMILY_AXES
@pytest.mark.parametrize("member", family.MEMBERS)
def test_a_retaining_target_read_of_a_family_member_retains_its_complete_predecessor(
    strategy: family.Strategy, layout: family.Layout, member: family.Member
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_family_row(strategy, layout, member)])))
    metadata, key, key_attribute = _family_member(strategy, layout, member)
    seen: list[object] = []

    def fn(tx: TxnAttempt) -> None:
        count, retained, document = tx.uow.acquire_rows(
            TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
        )
        assert count == 1 and retained is not None
        seen.append(document)
        completion = CompletionRequest(
            metadata, key_attribute, (retained,), None if document is None else (document,)
        )
        (completed,) = tx.uow.acquire_rows(completion, _member_rows)
        seen.append(completed)

    scope(port, family.MODEL).transact(fn, itself, concurrency="locking")
    assert seen == [_raw_document(layout, member), _COMPLETED_MEMBERS[member]]
    assert [type(call) for call in port.calls] == [BeginCall, ReadCall, CommitCall]


@family.FAMILY_AXES
@pytest.mark.parametrize("member", family.MEMBERS)
def test_a_coverage_read_of_a_family_member_reads_its_complete_predecessor(
    strategy: family.Strategy, layout: family.Layout, member: family.Member
) -> None:
    port = ScriptedAdapter(Transact(Read(rows=[_family_row(strategy, layout, member)])))
    metadata, _key, key_attribute = _family_member(strategy, layout, member)
    seen: list[tuple[list[tuple[object, ...]], list[object | None] | None]] = []

    def fn(tx: TxnAttempt) -> None:
        coverage = CoverageReadRequest(
            metadata,
            key_attribute,
            (CoverageTerm(1, (TimeInterval(_JAN, INFINITY),)),),
            locking=True,
        )
        seen.append(tx.uow.acquire_rows(coverage, _rows_and_documents))

    scope(port, family.MODEL).transact(fn, itself, concurrency="locking")
    ((rows, documents),) = seen
    assert rows == [_COMPLETED_MEMBERS[member]]
    raw = _raw_document(layout, member)
    assert documents == (None if raw is None else [raw])


@family.FAMILY_AXES
def test_a_family_members_retained_invalid_occurrence_stays_pending_until_its_completion(
    strategy: family.Strategy, layout: family.Layout
) -> None:
    invalid: dict[str, DocumentValue] = {
        **_FAMILY_PREDECESSORS["Holding"],
        "home": {"city": 7, "zone": "a"},
    }
    port = ScriptedAdapter(Transact(Read(rows=[_family_row(strategy, layout, "Holding", invalid)])))
    metadata, key, key_attribute = _family_member(strategy, layout, "Holding")
    refused: list[StoredDataDecodingError] = []

    def fn(tx: TxnAttempt) -> None:
        count, retained, document = tx.uow.acquire_rows(
            TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
        )
        assert count == 1 and retained is not None
        completion = CompletionRequest(
            metadata, key_attribute, (retained,), None if document is None else (document,)
        )
        with pytest.raises(StoredDataDecodingError) as caught:
            tx.uow.acquire_rows(completion, _member_rows)
        refused.append(caught.value)

    scope(port, family.MODEL).transact(fn, itself, concurrency="locking")
    (failure,) = refused
    assert failure.member == ValueObjectAttributeIdentity(
        ValueObjectIdentity(metadata.identity, ("home",)), "city"
    )
    assert [type(call) for call in port.calls] == [BeginCall, ReadCall, CommitCall]


@family.FAMILY_AXES
def test_a_family_members_retaining_read_refuses_an_invalid_attribute_at_the_read(
    strategy: family.Strategy, layout: family.Layout
) -> None:
    # The Attribute is judged at the read, as the narrow read judged it; the
    # invalid occurrence beside it is left to the completion.
    invalid: dict[str, DocumentValue] = {
        **_FAMILY_PREDECESSORS["Holding"],
        "home": {"city": 7, "zone": "a"},
    }
    if layout == "document":
        row = _family_row(strategy, layout, "Holding", {**invalid, "name": None})
        member = "name"
    else:
        # A native Column is trusted as the provider returned it; a temporal
        # end is host-checked.
        row = {**_family_row(strategy, layout, "Holding", invalid), "thru_z": None}
        member = "validEnd"
    port = ScriptedAdapter(Transact(Read(rows=[row])))
    metadata, key, _key_attribute = _family_member(strategy, layout, "Holding")
    refused: list[StoredDataDecodingError] = []

    def fn(tx: TxnAttempt) -> None:
        with pytest.raises(StoredDataDecodingError) as caught:
            tx.uow.acquire_rows(
                TargetReadRequest(metadata, key, _MAR, retains=True), consume_target
            )
        refused.append(caught.value)

    scope(port, family.MODEL).transact(fn, itself, concurrency="locking")
    (failure,) = refused
    view = inheritance.view(model_of(family.MODEL)).entity(metadata.identity)
    assert view is not None
    attribute = view.applicable_attribute(member)
    assert attribute is not None
    assert failure.member == attribute.identity
