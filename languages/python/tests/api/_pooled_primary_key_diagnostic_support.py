"""The frozen cases, counters, and readings of the pooled primary-key live diagnostic.

Every case is one representative insert flow measured against the live
database: one root per case, a first transaction read on its own, warm-up
transactions, then measured transactions, each graded by the Database Calls and
acquisitions it made and finally by the rows it stored. Elapsed time is read
around each transaction and around each insert call, so a call's own cost stays
apart from the flush and commit it shares with the rest of its transaction.

A case names one flow, one representation, and one Storage Layout, and the
mode says how its keys are stated. ``assigned`` supplies every key;
``generated`` omits it, so each insert takes its key from a KeySequence of
batch size 100 whose blocks the case's own root reserves. Each case inserts the
same rows under the same windows in every mode, so a generated reading compares
with the assigned one cell by cell, and a generated insert call is read apart
by whether it took its root's first reservation, a key the root already held,
or a refill.

The readings are diagnostics, not retained evidence: nothing here is a gate,
and nothing here is fed to the cost portfolio.
"""

from __future__ import annotations

import gc
import statistics
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from parallax.core import (
    AbstractRoot,
    Attr,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    ExecutionLifecycleHandler,
    ExecutionLifecycleHandlerError,
    KeySequence,
    RootExecution,
    TablePerHierarchy,
    TxTemporal,
    attr,
)
from parallax.core.execution_lifecycle import (
    AcquisitionFinished,
    AcquisitionStarted,
    ConnectionAcquired,
    DatabaseCallFinished,
    DatabaseCallStarted,
    DatabaseReadCompleted,
    DatabaseWriteCompleted,
    DatabaseWriteRowsCompleted,
    ExecutionEvent,
    ReadStarted,
)
from parallax.snapshot import TxnContext
from tests._support.pooled_key_diagnostic import DiagnosticRefused, Mode

__all__ = [
    "CASES",
    "CHECK",
    "MODELS",
    "NAMESPACE",
    "SCHEMA",
    "CallCounter",
    "Case",
    "CaseReading",
    "Protocol",
    "Tally",
    "capture_protocol",
    "check_stored",
    "readings_document",
    "run_case",
    "stored_state",
]

SCHEMA: Final = "parallax.diagnostic.pooled-primary-keys.live/1"

NAMESPACE: Final = "pooled.key.diagnostic"


class Plain(Entity, table="pkd_plain", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class PlainSheet(Entity, table="pkd_plain_sheet", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Versioned(Entity, table="pkd_versioned", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class VersionedSheet(Entity, table="pkd_versioned_sheet", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class Log(TxTemporal, table="pkd_log", namespace=NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class LogSheet(TxTemporal, table="pkd_log_sheet", namespace=NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Figure(
    Entity,
    table="pkd_figure",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class Disc(Figure, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="disc")):
    size: Attr[float]


class FigureSheet(
    Entity,
    table="pkd_figure_sheet",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
    layout=Document(),
):
    id: Attr[int] = attr(primary_key=True)
    label: Attr[str] = attr(max_length=16)


class DiscSheet(FigureSheet, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="disc")):
    size: Attr[float]


_BATCH_SIZE: Final = 100


def _generated(allocator: str) -> Any:
    return attr(primary_key=KeySequence(allocator, batch_size=_BATCH_SIZE))


class GeneratedPlain(Entity, table="pkd_g_plain", namespace=NAMESPACE):
    id: Attr[int] = _generated("pkd_g_plain_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedPlainSheet(
    Entity, table="pkd_g_plain_sheet", namespace=NAMESPACE, layout=Document()
):
    id: Attr[int] = _generated("pkd_g_plain_sheet_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedVersioned(Entity, table="pkd_g_versioned", namespace=NAMESPACE):
    id: Attr[int] = _generated("pkd_g_versioned_ids")
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class GeneratedVersionedSheet(
    Entity, table="pkd_g_versioned_sheet", namespace=NAMESPACE, layout=Document()
):
    id: Attr[int] = _generated("pkd_g_versioned_sheet_ids")
    label: Attr[str] = attr(max_length=16)
    version: Attr[int] = attr(optimistic_locking=True)


class GeneratedLog(TxTemporal, table="pkd_g_log", namespace=NAMESPACE):
    id: Attr[int] = _generated("pkd_g_log_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedLogSheet(
    TxTemporal, table="pkd_g_log_sheet", namespace=NAMESPACE, layout=Document()
):
    id: Attr[int] = _generated("pkd_g_log_sheet_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedFigure(
    Entity,
    table="pkd_g_figure",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
):
    id: Attr[int] = _generated("pkd_g_figure_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedDisc(
    GeneratedFigure, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="disc")
):
    size: Attr[float]


class GeneratedFigureSheet(
    Entity,
    table="pkd_g_figure_sheet",
    namespace=NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy("kind")),
    layout=Document(),
):
    id: Attr[int] = _generated("pkd_g_figure_sheet_ids")
    label: Attr[str] = attr(max_length=16)


class GeneratedDiscSheet(
    GeneratedFigureSheet, namespace=NAMESPACE, inheritance=ConcreteSubtype(tag_value="disc")
):
    size: Attr[float]


MODELS: Final[Mapping[Mode, DomainModel]] = {
    "assigned": DomainModel(
        Plain,
        PlainSheet,
        Versioned,
        VersionedSheet,
        Log,
        LogSheet,
        Figure,
        Disc,
        FigureSheet,
        DiscSheet,
    ),
    "generated": DomainModel(
        GeneratedPlain,
        GeneratedPlainSheet,
        GeneratedVersioned,
        GeneratedVersionedSheet,
        GeneratedLog,
        GeneratedLogSheet,
        GeneratedFigure,
        GeneratedDisc,
        GeneratedFigureSheet,
        GeneratedDiscSheet,
    ),
}
"""Each mode's model: the same tables' shapes, one supplying keys and one
generating them."""

_GENERATED: Final[Mapping[type[Entity], type[Entity]]] = {
    Plain: GeneratedPlain,
    PlainSheet: GeneratedPlainSheet,
    Versioned: GeneratedVersioned,
    VersionedSheet: GeneratedVersionedSheet,
    Log: GeneratedLog,
    LogSheet: GeneratedLogSheet,
    Disc: GeneratedDisc,
    DiscSheet: GeneratedDiscSheet,
}

type Flow = Literal[
    "plain", "versioned", "temporal", "inheritance", "amend-pending", "amend-flushed", "batch"
]
type Representation = Literal["typed", "wire"]
type Layout = Literal["columns", "document"]

_INSERTED: Final = "inserted"
_AMENDED: Final = "amended"
_SIZE: Final = 2.5


@dataclass(frozen=True, slots=True)
class Tally:
    """What one transaction did: acquisitions it made, its Database Calls by
    kind, and how many of its Reads were key reservations, each of which made
    one of those acquisitions and one of those reads."""

    acquisitions: int = 0
    reads: int = 0
    writes: int = 0
    reservations: int = 0

    def reserving(self, reservations: int) -> Tally:
        """This tally with ``reservations`` key reservations beside it."""
        return Tally(
            self.acquisitions + reservations,
            self.reads + reservations,
            self.writes,
            self.reservations + reservations,
        )


@dataclass(frozen=True, slots=True)
class Protocol:
    """How many transactions a case runs before, and while, it is measured."""

    warmup: int
    repeats: int


CHECK: Final = Protocol(warmup=0, repeats=1)
"""What a run with no output asks of each case: one transaction, fully graded."""

_CAPTURE: Final = Protocol(warmup=50, repeats=200)
_CAPTURE_LARGE_BATCH: Final = Protocol(warmup=5, repeats=30)
_LARGE_BATCH: Final = 1_000


@dataclass(frozen=True, slots=True)
class Case:
    """One frozen flow: the entity it inserts, how many rows each transaction
    inserts, and what each transaction must cost in calls and acquisitions."""

    flow: Flow
    representation: Representation
    layout: Layout
    entity: type[Entity]
    expected: Tally
    rows: int = 1

    @property
    def id(self) -> str:
        scope = f"batch.{self.rows}" if self.flow == "batch" else self.flow
        return f"{scope}.{self.layout}.{self.representation}"

    def table(self, mode: Mode) -> str:
        return _TABLES[self.entity] if mode == "assigned" else _TABLES[_GENERATED[self.entity]]

    def inserted(self, mode: Mode) -> type[Entity]:
        return self.entity if mode == "assigned" else _GENERATED[self.entity]

    @property
    def amended(self) -> bool:
        return self.flow in {"amend-pending", "amend-flushed"}


_TABLES: Final[Mapping[type[Entity], str]] = {
    Plain: "pkd_plain",
    PlainSheet: "pkd_plain_sheet",
    Versioned: "pkd_versioned",
    VersionedSheet: "pkd_versioned_sheet",
    Log: "pkd_log",
    LogSheet: "pkd_log_sheet",
    Disc: "pkd_figure",
    DiscSheet: "pkd_figure_sheet",
    GeneratedPlain: "pkd_g_plain",
    GeneratedPlainSheet: "pkd_g_plain_sheet",
    GeneratedVersioned: "pkd_g_versioned",
    GeneratedVersionedSheet: "pkd_g_versioned_sheet",
    GeneratedLog: "pkd_g_log",
    GeneratedLogSheet: "pkd_g_log_sheet",
    GeneratedDisc: "pkd_g_figure",
    GeneratedDiscSheet: "pkd_g_figure_sheet",
}

_ONE_WRITE: Final = Tally(acquisitions=1, writes=1)
_READ_THEN_WRITES: Final = Tally(acquisitions=1, reads=1, writes=2)


def _representatives(
    flow: Flow, columns: type[Entity], document: type[Entity], expected: Tally
) -> tuple[Case, Case]:
    return (
        Case(flow, "typed", "columns", columns, expected),
        Case(flow, "wire", "document", document, expected),
    )


CASES: Final[tuple[Case, ...]] = (
    *_representatives("plain", Plain, PlainSheet, _ONE_WRITE),
    *_representatives("versioned", Versioned, VersionedSheet, _ONE_WRITE),
    *_representatives("temporal", Log, LogSheet, _ONE_WRITE),
    *_representatives("inheritance", Disc, DiscSheet, _ONE_WRITE),
    *_representatives("amend-pending", Plain, PlainSheet, _ONE_WRITE),
    *_representatives("amend-flushed", Plain, PlainSheet, _READ_THEN_WRITES),
    Case("batch", "typed", "columns", Plain, _ONE_WRITE, rows=2),
    Case("batch", "typed", "columns", Plain, _ONE_WRITE, rows=_LARGE_BATCH),
)


def capture_protocol(case: Case) -> Protocol:
    return _CAPTURE_LARGE_BATCH if case.rows >= _LARGE_BATCH else _CAPTURE


class CallCounter:
    """A lifecycle Provider counting each transaction's acquisitions and Database
    Calls, refusing anything that did not complete.

    Counting is all it does per event, so a measured transaction pays the same
    small cost in every mode. Refusals are kept rather than raised inside a
    Handler, and :meth:`take` raises the first one.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: list[_Counting] = []
        self._refusals: list[str] = []

    def open(self, execution: RootExecution, /) -> ExecutionLifecycleHandler | None:
        handler = _Counting(self)
        with self._lock:
            self._handlers.append(handler)
        return handler

    def report_handler_error(self, error: ExecutionLifecycleHandlerError, /) -> None:
        self.refuse(f"a lifecycle handler failed: {error!r}")

    def refuse(self, reason: str) -> None:
        with self._lock:
            self._refusals.append(reason)

    def take(self) -> Tally:
        """Everything counted since the last take, once every execution it
        opened has finished every call and acquisition it started."""
        with self._lock:
            handlers, self._handlers = self._handlers, []
            refusals, self._refusals = self._refusals, []
        for handler in handlers:
            refusals.extend(handler.unfinished())
        if refusals:
            raise DiagnosticRefused("; ".join(refusals))
        return Tally(
            acquisitions=sum(handler.acquisitions for handler in handlers),
            reads=sum(handler.reads for handler in handlers),
            writes=sum(handler.writes for handler in handlers),
            reservations=sum(handler.reservations for handler in handlers),
        )


_COMPLETED: Final = (DatabaseReadCompleted, DatabaseWriteCompleted, DatabaseWriteRowsCompleted)


class _Counting:
    __slots__ = (
        "_acquiring",
        "_calling",
        "_counter",
        "acquisitions",
        "reads",
        "reservations",
        "writes",
    )

    def __init__(self, counter: CallCounter) -> None:
        self._counter = counter
        self._acquiring: set[int] = set()
        self._calling: set[int] = set()
        self.acquisitions = 0
        self.reads = 0
        self.writes = 0
        self.reservations = 0

    def handle(self, event: ExecutionEvent, /) -> None:
        if isinstance(event, ReadStarted):
            self.reservations += event.purpose == "reservation"
        elif isinstance(event, AcquisitionStarted):
            self._acquiring.add(event.activity_id)
            self.acquisitions += 1
        elif isinstance(event, AcquisitionFinished):
            self._acquisition_finished(event)
        elif isinstance(event, DatabaseCallStarted):
            self._calling.add(event.activity_id)
            if event.kind == "read":
                self.reads += 1
            else:
                self.writes += 1
        elif isinstance(event, DatabaseCallFinished):
            self._call_finished(event)

    def _acquisition_finished(self, event: AcquisitionFinished) -> None:
        if event.activity_id not in self._acquiring:
            self._counter.refuse(f"acquisition {event.activity_id} finished unstarted")
        self._acquiring.discard(event.activity_id)
        if not isinstance(event.outcome, ConnectionAcquired):
            self._counter.refuse(f"acquisition {event.activity_id} failed: {event.outcome!r}")

    def _call_finished(self, event: DatabaseCallFinished) -> None:
        if event.activity_id not in self._calling:
            self._counter.refuse(f"database call {event.activity_id} finished unstarted")
        self._calling.discard(event.activity_id)
        if not isinstance(event.outcome, _COMPLETED):
            self._counter.refuse(
                f"database call {event.activity_id} did not complete: {event.outcome!r}"
            )

    def unfinished(self) -> list[str]:
        return [
            *(f"acquisition {activity} never finished" for activity in sorted(self._acquiring)),
            *(f"database call {activity} never finished" for activity in sorted(self._calling)),
        ]


type _Handout = Literal["first", "local", "refill"]


def _handout(key: int) -> _Handout:
    """Which of its root's handouts the generated insert of ``key`` is: keys
    are handed out in order from blocks of ``_BATCH_SIZE``, so the first key
    of every block but the first refills."""
    if key == 1:
        return "first"
    return "refill" if (key - 1) % _BATCH_SIZE == 0 else "local"


@dataclass(slots=True)
class CaseReading:
    """One case's readings: nanoseconds per transaction and per insert call,
    and the tally every transaction it measured agreed on beside its key
    reservations. A generated reading also keeps each measured insert call's
    nanoseconds by whether it handed out a held key or refilled."""

    case: Case
    mode: Mode
    protocol: Protocol
    first_transaction_ns: int
    first_insert_ns: int
    transaction_ns: list[int] = field(default_factory=list[int])
    insert_ns: list[int] = field(default_factory=list[int])
    local_insert_ns: list[int] = field(default_factory=list[int])
    refill_insert_ns: list[int] = field(default_factory=list[int])
    reservations: int = 0
    tally: Tally = field(default_factory=Tally)

    def document(self) -> dict[str, object]:
        document: dict[str, object] = {
            "id": self.case.id,
            "flow": self.case.flow,
            "representation": self.case.representation,
            "layout": self.case.layout,
            "rows": self.case.rows,
            "protocol": {"warmup": self.protocol.warmup, "repeats": self.protocol.repeats},
            "firstTransactionNs": self.first_transaction_ns,
            "firstInsertNs": self.first_insert_ns,
            "transactionNs": _summary(self.transaction_ns),
            "insertNs": _summary(self.insert_ns),
            "perTransaction": {
                "acquisitions": self.tally.acquisitions,
                "reads": self.tally.reads,
                "writes": self.tally.writes,
            },
        }
        if self.mode == "generated":
            document["handouts"] = {
                "firstReservationInsertNs": self.first_insert_ns,
                "localInsertNs": _summary(self.local_insert_ns),
                "refillInsertNs": _summary(self.refill_insert_ns),
                "measuredReservations": self.reservations,
            }
        return document


def _summary(samples: Sequence[int]) -> dict[str, object]:
    if not samples:
        return {"count": 0, "samples": []}
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "median": statistics.median(ordered),
        "min": ordered[0],
        "max": ordered[-1],
        "samples": list(samples),
    }


class _Keys:
    """The keys each transaction of one case inserts, supplied in assigned
    mode and handed out in the same order in generated mode."""

    __slots__ = ("next",)

    def __init__(self) -> None:
        self.next = 1

    def take(self, count: int) -> range:
        taken = range(self.next, self.next + count)
        self.next += count
        return taken


def _name(entity: type[Entity]) -> str:
    return f"{NAMESPACE}.{entity.__name__}"


def _typed_draft(case: Case, mode: Mode, key: int) -> Entity:
    entity: Any = case.inserted(mode)
    stated: dict[str, object] = {"label": _INSERTED}
    if mode == "assigned":
        stated["id"] = key
    if case.flow == "inheritance":
        stated["size"] = _SIZE
    return entity(**stated)


def _wire_payload(case: Case, mode: Mode, key: int) -> dict[str, object]:
    payload: dict[str, object] = {"label": _INSERTED}
    if mode == "assigned":
        payload["id"] = key
    if case.flow == "inheritance":
        payload["size"] = _SIZE
    return payload


def _insert(tx: TxnContext, case: Case, mode: Mode, key: int) -> tuple[object, int]:
    """Insert ``key`` the way ``case`` and ``mode`` state it, answering the
    value that now carries the insertion and the call's own elapsed
    nanoseconds."""
    if case.representation == "typed":
        draft = _typed_draft(case, mode, key)
        started = time.perf_counter_ns()
        inserted = tx.insert(draft)
        return inserted, time.perf_counter_ns() - started
    payload = _wire_payload(case, mode, key)
    started = time.perf_counter_ns()
    node = tx.wire.insert(_name(case.inserted(mode)), payload)
    return node, time.perf_counter_ns() - started


def _read(tx: TxnContext, case: Case, mode: Mode, key: int) -> None:
    entity: Any = case.inserted(mode)
    if case.representation == "typed":
        tx.find(entity.where(entity.id == key)).result()
        return
    name = _name(entity)
    tx.wire.find(
        {"target": name, "predicate": {"eq": {"path": f"{name}.id", "value": key}}}
    ).result()


def _amend(tx: TxnContext, case: Case, inserted: Any) -> None:
    if case.representation == "typed":
        tx.amend(inserted.edit(label=_AMENDED))
    else:
        tx.wire.amend(inserted, {"label": _AMENDED})


def _transaction(
    case: Case, mode: Mode, keys: range, calls: list[tuple[int, int]]
) -> Callable[[TxnContext], None]:
    def body(tx: TxnContext) -> None:
        for key in keys:
            inserted, elapsed = _insert(tx, case, mode, key)
            calls.append((key, elapsed))
            if case.flow == "amend-flushed":
                _read(tx, case, mode, key)
            if case.amended:
                _amend(tx, case, inserted)

    return body


def run_case(
    db: Any, counter: CallCounter, case: Case, mode: Mode, protocol: Protocol
) -> CaseReading:
    """Run ``case`` in ``mode`` on ``db``, a fresh root counted by ``counter``:
    one first transaction, ``protocol``'s warm-up, then its measured
    transactions, each of which must tally exactly what the case expects beside
    the reservations its keys' positions in their blocks call for."""
    keys = _Keys()
    counter.take()

    def measured(calls: list[tuple[int, int]]) -> tuple[int, int]:
        taken = keys.take(case.rows)
        reserving = 0 if mode == "assigned" else sum(_handout(key) != "local" for key in taken)
        expected = case.expected.reserving(reserving)
        body = _transaction(case, mode, taken, calls)
        started = time.perf_counter_ns()
        db.transact(body)
        elapsed = time.perf_counter_ns() - started
        tally = counter.take()
        if tally != expected:
            raise DiagnosticRefused(f"{case.id} made {tally}, not {expected}")
        return elapsed, reserving

    first_calls: list[tuple[int, int]] = []
    first, _ = measured(first_calls)
    reading = CaseReading(case, mode, protocol, first, first_calls[0][1], tally=case.expected)
    for _ in range(protocol.warmup):
        measured([])
    gc.collect()
    for _ in range(protocol.repeats):
        calls: list[tuple[int, int]] = []
        elapsed, reserving = measured(calls)
        reading.transaction_ns.append(elapsed)
        reading.reservations += reserving
        reading.insert_ns.extend(call for _, call in calls)
        if mode == "generated":
            for key, call in calls:
                handouts = (
                    reading.refill_insert_ns
                    if _handout(key) == "refill"
                    else (reading.local_insert_ns)
                )
                handouts.append(call)
    return reading


def stored_state(profile_run: Any, case: Case, mode: Mode) -> tuple[int, int, int, set[str]]:
    """How many current rows ``case``'s table holds in ``mode``, its least and
    greatest key, and every label it stores."""
    label = "payload->>'label'" if case.layout == "document" else "label"
    current = " where out_z = 'infinity'" if case.flow == "temporal" else ""
    table = case.table(mode)
    ((count, least, greatest),) = profile_run.port.execute(
        f"select count(*), min(id), max(id) from px.{table}{current}", []
    )
    labels = {
        str(row[0])
        for row in profile_run.port.execute(f"select distinct {label} from px.{table}{current}", [])
    }
    return int(count), int(least), int(greatest), labels


def check_stored(profile_run: Any, case: Case, mode: Mode, transactions: int) -> None:
    """Refuse a case whose table holds anything but its own inserts, each
    labelled as its flow leaves it, keyed one through the number inserted."""
    expected_rows = transactions * case.rows
    expected_label = _AMENDED if case.amended else _INSERTED
    observed = stored_state(profile_run, case, mode)
    if observed != (expected_rows, 1, expected_rows, {expected_label}):
        raise DiagnosticRefused(
            f"{case.id} stored {observed}, not "
            f"{(expected_rows, 1, expected_rows, {expected_label})}"
        )


def readings_document(
    mode: Mode, readings: Sequence[CaseReading], server_version: str
) -> dict[str, object]:
    """The readings in the frozen output schema, refusing an incomplete set."""
    measured = [reading.case.id for reading in readings]
    if measured != [case.id for case in CASES]:
        raise DiagnosticRefused(f"the readings cover {measured}, not every frozen case")
    return {
        "schema": SCHEMA,
        "mode": mode,
        "postgresServerVersion": server_version,
        "cases": [reading.document() for reading in readings],
    }
