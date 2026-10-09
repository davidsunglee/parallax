"""The Attempt's row acquisition over a scripted port (`m-execution`): each
read in its own activity bracket, the read's resources settled however its
consumer leaves, and a target read decided by its root count once its Read has
closed."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from typing import Any, Final, cast

import pytest

from parallax.conformance import models
from parallax.conformance._lifecycle_recording import RecordingLifecycleProvider
from parallax.conformance.class_models import MODELS
from parallax.core import Attr, Bitemporal, Document, DomainModel, ValueObject, attr
from parallax.core.base import INFINITY, SQL_NULL, DocumentValue, PresentDocument
from parallax.core.db_error import DatabaseError
from parallax.core.db_port import MappingRow
from parallax.core.document_codec import _document as document_module
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
from parallax.core.metamodel import (
    AttributeIdentity,
    ValueObjectAttributeIdentity,
    ValueObjectIdentity,
    entity_by_name,
)
from parallax.core.read_delivery import StoredDataDecodingError
from parallax.core.read_delivery._row_converter import ReadRowConverter
from parallax.core.temporal_read import TimeInterval
from parallax.core.unit_work import CardinalityCorruptionError, TargetWrite
from parallax.core.unit_work.acquisition import (
    CompletionRequest,
    CoverageReadRequest,
    CoverageTerm,
    TargetReadRequest,
    consume_target,
)
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

    def fn(tx: Attempt) -> None:
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

    def fn(tx: Attempt) -> None:
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

    def fn(tx: Attempt) -> None:
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

    def amend(tags: list[str]) -> PreparedTargetWrite:
        return prepare_wire_write(
            TargetWrite(
                "amend",
                metadata.identity.canonical,
                {"id": 1, "tags": tags},
                if_tx_start=_T0,
                valid_from=_MAR,
            ),
            model_of(_HULLS),
        )

    def fn(tx: Attempt) -> None:
        tx.target_write(amend(["a"]))
        assert interpreted == ["tags"]
        tx.target_write(amend(["b", "b"]))
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

    def fn(tx: Attempt) -> None:
        tx.target_write(
            prepare_wire_write(
                TargetWrite(
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

    def fn(tx: Attempt) -> None:
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
    # the call has returned and inside the write batch, with no read of its own;
    # a scalar collection inside it is judged with it.
    recorder = RecordingLifecycleProvider()
    spec, failing = _INVALID_SPECS[invalid]
    row = _hull_row(entity, {**_VALID, "spec": spec})
    port = ScriptedAdapter(Transact(Read(rows=[row])))
    metadata, _key = _hull_keys(entity)
    called: list[str] = []

    def fn(tx: Attempt) -> None:
        tx.target_write(
            prepare_wire_write(
                TargetWrite(
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
    batch = next(
        index for index, event in enumerate(events) if isinstance(event, WriteBatchStarted)
    )
    assert events.index(read) < batch
    assert not any(isinstance(event, DatabaseCallStarted) for event in events[batch:])


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

    def fn(tx: Attempt) -> None:
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

    def fn(tx: Attempt) -> None:
        with pytest.raises(StoredDataDecodingError) as caught:
            tx.target_write(
                prepare_wire_write(
                    TargetWrite(
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
