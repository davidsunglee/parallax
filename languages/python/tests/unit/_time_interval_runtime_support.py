"""Independently selectable runtime workloads over Valid-Time windows,
coverage, and open bounds, driven through the public interfaces over
provider-free ports.

A *flow cell* names one public operation, its Typed or Wire interface, its
Columns or document layout, and a preparation mode:

* ``source-keyed`` — one bounded Bitemporal update of a node the transaction
  read, producing a close and a head, middle, and tail successor;
* ``predicate`` — one bounded Bitemporal ``update_where`` resolving and
  revising 32 targets;
* ``target-patch`` — one caller-addressed bounded Wire patch;
* ``target-replace`` — one caller-addressed bounded replacement across three
  stored intervals and the two gaps between them;
* ``read-eager`` — one fully delivered 128-root Latest/Latest Bitemporal find;
* ``read-stream`` — the same query consumed completely in 32-root pages.

Every write window opens at the public verb and closes once ``transact`` has
returned: preparation, buffering, any read the write makes itself (a
resolving read, a coverage read at flush), the pre-commit flush's planning,
settlement, and SQL lowering, production bind adaptation, psycopg's dump of
every bind, and the provider-free commit. A read the caller makes to obtain a
source is outside it. Every read window is one complete delivery. Public
writes prepare every invocation, so they have a preparation-inclusive mode
only. A read is measured both ways: ``preparation-inclusive`` over a root whose
read-plan cache holds nothing (capacity zero), so every delivery compiles its
plan; ``reused-execution`` over a root whose cache already holds the compiled
plan before the first sample. In both modes the prepared model and the root are
composed once, outside every window.

An *algorithm cell* names one shared interval algorithm and an input size, and
drives the owner of that algorithm through the public verbs of one Typed
Columns transaction:

* ``replacement-gaps`` — ``size`` adjacent caller-addressed replacements of one
  object, over ``size / 2`` stored intervals each followed by a gap, so stored
  coverage spans replacement segments; the window is the whole transaction,
  including the coverage read and gap filling at flush;
* ``destruction-merge`` — an insertion stored as ``size`` tagged rows, each
  terminated in a barrier region of its own, authored in an order that differs
  from Valid-Time order; the window is the reinsertion verb whose admission
  depends on that destruction coverage;
* ``removal-window`` — the same stored insertion, admitted over the pending
  removal of an earlier insertion from an earlier anchor, so the flush storing
  it moves the retained anchor, and then given a pending partial removal; the
  window is four refused reinsertions, then (outside it) a flush that removes
  one tagged row, then four refused reinsertions again.

The provider-free ports cross every statement's binds, a read's as much as a
write's, through the production PostgreSQL bind adaptation and psycopg's dump
under the adapter map the PostgreSQL port configures on every connection it
initializes, so a revision's own registered adapters are the ones measured; a
read answers composed rows and a write reports one affected row. They neither
execute SQL nor commit anything: these readings never measure PostgreSQL
execution, network, or commit latency.

Every run reports an :class:`Outcome` counted from the port over the whole run,
and :func:`expected_outcome` states what a complete run of each cell reports, so
a run that stopped early or took another path is refused rather than timed.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import copy
import datetime as dt
import gc
import hashlib
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter_ns
from types import SimpleNamespace
from typing import Any, Final, Literal, cast

import psycopg
from psycopg import postgres
from psycopg.abc import Buffer
from psycopg.adapt import AdaptersMap, PyFormat, Transformer
from psycopg.rows import TupleRow

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import LATEST, DomainModel, Entity
from parallax.core.base import INFINITY
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.postgres._connection import adapt_binds, initialize_connection
from parallax.snapshot import ServingModel, prepare_model
from parallax.snapshot.handle import (
    Database,
    ExecutionFailure,
    KeyedWriteValueError,
    ScopedDatabase,
    Transaction,
)
from parallax.snapshot.handle._read_plan import DEFAULT_READ_PLAN_CACHE_CAPACITY
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_rows
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _write_lowering_support as lowering_support

__all__ = [
    "ALGORITHMS",
    "CELLS",
    "EXECUTION_SEAM",
    "FLOWS",
    "INTERFACES",
    "LAYOUTS",
    "MODES",
    "NOT_APPLICABLE",
    "PORT_ADAPTERS",
    "SIZES",
    "AlgorithmCell",
    "Cell",
    "Description",
    "Driver",
    "FlowCell",
    "NotApplicable",
    "Outcome",
    "Reading",
    "Stopwatch",
    "cell_named",
    "description",
    "driver",
    "expected_outcome",
    "measure",
    "serialize",
    "support_digest",
]

type Flow = Literal[
    "source-keyed", "predicate", "target-patch", "target-replace", "read-eager", "read-stream"
]
type Interface = Literal["typed", "wire"]
type Layout = Literal["columns", "document"]
type Mode = Literal["preparation-inclusive", "reused-execution"]
type Algorithm = Literal["replacement-gaps", "destruction-merge", "removal-window"]

FLOWS: Final[tuple[Flow, ...]] = (
    "source-keyed",
    "predicate",
    "target-patch",
    "target-replace",
    "read-eager",
    "read-stream",
)
INTERFACES: Final[tuple[Interface, ...]] = ("typed", "wire")
LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
MODES: Final[tuple[Mode, ...]] = ("preparation-inclusive", "reused-execution")
ALGORITHMS: Final[tuple[Algorithm, ...]] = (
    "replacement-gaps",
    "destruction-merge",
    "removal-window",
)
SIZES: Final[tuple[int, ...]] = (8, 32, 128)

_WRITE_FLOWS: Final[frozenset[Flow]] = frozenset(
    {"source-keyed", "predicate", "target-patch", "target-replace"}
)
_PREDICATE_TARGETS: Final = 32
_READ_ROOTS: Final = 128
_PAGE_SIZE: Final = 32
_REFUSALS_PER_WINDOW: Final = 4
_STRIDE: Final = 5
"""The destruction workload's i-th termination removes row ``(i * 5) % size``:
five is coprime with every size, so the order visits every row, neither
ascending nor descending."""

EXECUTION_SEAM: Final = (
    "provider-free in-process ports: every statement's binds, read or write, cross the "
    "production PostgreSQL bind adaptation and psycopg's dump under the adapter map the "
    "PostgreSQL port configures on each connection; reads answer composed rows and writes "
    "report one affected row; no SQL executes and nothing commits, so no PostgreSQL "
    "execution, network, or commit latency is measured"
)
_EDITION: Final = "time-interval-runtime"
_DAY: Final = dt.timedelta(days=1)
_ORIGIN: Final = lowering_support.VALID_START
_KEY: Final = 7
"""The object the destruction and removal workloads insert, split, and remove."""
_PREVIOUS_ANCHOR: Final = _ORIGIN - _DAY
"""Where the removal workload's superseded insertion of :data:`_KEY` starts."""
_TARGET_KEY: Final = 901
"""The stored object the replacement workloads address."""


@dataclass(frozen=True, slots=True)
class FlowCell:
    flow: Flow
    interface: Interface
    layout: Layout
    mode: Mode

    @property
    def id(self) -> str:
        return f"flow/{self.flow}/{self.interface}/{self.layout}/{self.mode}"


@dataclass(frozen=True, slots=True)
class AlgorithmCell:
    algorithm: Algorithm
    size: int

    @property
    def id(self) -> str:
        return f"algorithm/{self.algorithm}/{self.size}"


type Cell = FlowCell | AlgorithmCell


@dataclass(frozen=True, slots=True)
class NotApplicable:
    """A flow combination no public lifecycle supports, and why; recorded
    beside every capture so its absence is a stated fact, not missing
    evidence."""

    flow: Flow
    interface: Interface
    mode: Mode
    reason: str


def _interfaces(flow: Flow) -> tuple[Interface, ...]:
    return ("wire",) if flow == "target-patch" else INTERFACES


def _modes(flow: Flow) -> tuple[Mode, ...]:
    return ("preparation-inclusive",) if flow in _WRITE_FLOWS else MODES


CELLS: Final[tuple[Cell, ...]] = (
    *(
        FlowCell(flow, interface, layout, mode)
        for flow in FLOWS
        for interface in _interfaces(flow)
        for layout in LAYOUTS
        for mode in _modes(flow)
    ),
    *(AlgorithmCell(algorithm, size) for algorithm in ALGORITHMS for size in SIZES),
)

_NO_PREPARED_WRITE: Final = (
    "a public write prepares its instruction on every invocation; no reusable prepared-write "
    "execution exists to measure"
)
_NO_TYPED_PATCH: Final = "no public Typed target-patch verb exists; a Typed target replaces"

NOT_APPLICABLE: Final[tuple[NotApplicable, ...]] = (
    *(
        NotApplicable(flow, interface, "reused-execution", _NO_PREPARED_WRITE)
        for flow in FLOWS
        if flow in _WRITE_FLOWS
        for interface in _interfaces(flow)
    ),
    *(NotApplicable("target-patch", "typed", mode, _NO_TYPED_PATCH) for mode in MODES),
)


def cell_named(name: str) -> Cell:
    for cell in CELLS:
        if cell.id == name:
            return cell
    raise KeyError(f"{name!r} is not a supported time-interval runtime cell")


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one run did, counted at its port over the whole run: statements
    executed, reads answered, roots delivered, reinsertions refused and
    admitted."""

    statements: int = 0
    reads: int = 0
    roots: int = 0
    refused: int = 0
    admitted: int = 0

    def document(self) -> dict[str, int]:
        return {
            "statements": self.statements,
            "reads": self.reads,
            "roots": self.roots,
            "refused": self.refused,
            "admitted": self.admitted,
        }


def expected_outcome(cell: Cell) -> Outcome:
    """What one complete run of ``cell`` reports."""
    if isinstance(cell, AlgorithmCell):
        size = cell.size
        if cell.algorithm == "replacement-gaps":
            return Outcome(statements=2 * size, reads=1)
        if cell.algorithm == "destruction-merge":
            return Outcome(statements=size + 1, reads=size // 2 + size, admitted=1)
        return Outcome(statements=size + 4, reads=size // 2 + 4, refused=2 * _REFUSALS_PER_WINDOW)
    match cell.flow:
        case "source-keyed" | "target-patch":
            return Outcome(statements=4, reads=1)
        case "target-replace":
            return Outcome(statements=10, reads=1)
        case "predicate":
            return Outcome(statements=4 * _PREDICATE_TARGETS, reads=1)
        case "read-eager":
            return Outcome(reads=1, roots=_READ_ROOTS)
        case "read-stream":
            return Outcome(reads=_READ_ROOTS // _PAGE_SIZE, roots=_READ_ROOTS)


_SETUP: Final = (
    "the prepared model, the root, and the provider-free port are composed once, outside "
    "every window"
)
_FLOW_STAGES: Final[Mapping[Flow, str]] = {
    "source-keyed": (
        "a bounded Bitemporal tx.update or tx.wire.update over a node read before the window: "
        "verb, preparation, buffering, pre-commit flush (planning, settlement, SQL lowering), "
        "bind adaptation and dump of the close and three successors, and transact's return"
    ),
    "predicate": (
        "a bounded Bitemporal tx.update_where or tx.wire.update_where: verb, preparation, the "
        "resolving read over 32 rows, materialization and buffering, the pre-commit flush of "
        "32 closes and 96 successors, bind adaptation and dump, and transact's return"
    ),
    "target-patch": (
        "a caller-addressed bounded tx.wire.update stating if_tx_start: verb, preparation, "
        "buffering, the flush's coverage read and starting-revision check, settlement, SQL "
        "lowering, bind adaptation and dump, and transact's return"
    ),
    "target-replace": (
        "a caller-addressed bounded tx.replace or tx.wire.replace stating if_tx_start over "
        "three stored intervals and two gaps: verb, preparation, the flush's coverage read and "
        "starting-revision check, settlement with gap filling, SQL lowering, bind adaptation "
        "and dump, and transact's return"
    ),
    "read-eager": (
        "one db.find or db.wire.find delivering all 128 Latest/Latest roots, including its "
        "statement's bind adaptation and dump"
    ),
    "read-stream": (
        "one db.stream or db.wire.stream over the same query, consumed to its last root in "
        "32-root pages, including every page statement's bind adaptation and dump"
    ),
}
_MODE_SETUP: Final[Mapping[Mode, str]] = {
    "preparation-inclusive": (
        "; the root's read-plan cache has capacity zero, so every delivery inside the window "
        "compiles its read plan"
    ),
    "reused-execution": (
        "; one delivery outside the window compiles the plan into the root's read-plan cache, "
        "so every delivery inside it reuses that plan"
    ),
}
_ALGORITHM_STAGES: Final[Mapping[Algorithm, str]] = {
    "replacement-gaps": (
        "size adjacent caller-addressed tx.replace calls stating if_tx_start, then the flush's "
        "coverage read over size/2 stored intervals with gaps, composition, gap filling, SQL "
        "lowering, bind adaptation and dump, and transact's return"
    ),
    "destruction-merge": (
        "one tx.insert reinserting an object whose stored insertion spans size tagged rows, "
        "each terminated in its own barrier region in an order differing from Valid-Time "
        "order: the verb's repeated-insertion and removal checks over that destruction "
        "coverage, and buffering"
    ),
    "removal-window": (
        "four refused reinsertions of an object whose stored insertion spans size tagged rows "
        "under a pending partial removal, that insertion having been admitted over the "
        "removal of an earlier one from an earlier anchor before the window, then, after a "
        "flush outside the window removes one tagged row, four refused reinsertions under a "
        "new pending partial removal"
    ),
}
_ALGORITHM_SETUP: Final = (
    "; one transaction per run: the insertion, its splitting flush, the source reads, and "
    "the pending writes are outside the window, and the transaction is abandoned after it"
)


@dataclass(frozen=True, slots=True)
class Description:
    stages: str
    setup: str
    units: int


def description(cell: Cell) -> Description:
    """What ``cell``'s window contains, what is composed outside it, and how
    many units (targets, roots, or input size) one run covers."""
    if isinstance(cell, AlgorithmCell):
        return Description(_ALGORITHM_STAGES[cell.algorithm], _SETUP + _ALGORITHM_SETUP, cell.size)
    if cell.flow in _WRITE_FLOWS:
        units = _PREDICATE_TARGETS if cell.flow == "predicate" else 1
        return Description(_FLOW_STAGES[cell.flow], _SETUP, units)
    return Description(_FLOW_STAGES[cell.flow], _SETUP + _MODE_SETUP[cell.mode], _READ_ROOTS)


@dataclass(slots=True)
class Stopwatch:
    """The timed region of one run: each ``start``/``stop`` pair adds one
    window, and a run's sample is their sum."""

    elapsed_ns: int = 0
    windows: int = 0
    _started: int | None = field(default=None, repr=False)

    def start(self) -> None:
        if self._started is not None:
            raise RuntimeError("a window is already open")
        self._started = perf_counter_ns()

    def stop(self) -> None:
        stopped = perf_counter_ns()
        started = self._started
        if started is None:
            raise RuntimeError("no window is open")
        self._started = None
        self.elapsed_ns += stopped - started
        self.windows += 1


@dataclass(frozen=True, slots=True)
class Driver:
    """One cell's composed workload: ``run`` performs one complete run timed
    by the stopwatch it is handed, and ``counts`` answers what the port has
    counted of the current run so far."""

    run: Callable[[Stopwatch], Outcome]
    counts: Callable[[], Outcome]


class _SessionInfo:
    """The two connection parameters the port's initialization checks."""

    encoding = "utf-8"

    def parameter_status(self, name: str) -> str | None:
        return "ISO, MDY" if name == "DateStyle" else None


def _port_adapters() -> AdaptersMap:
    """A connection's own adapter map over psycopg's defaults, configured by the
    port's own connection initialization."""
    adapters = AdaptersMap(postgres.adapters)
    session = SimpleNamespace(adapters=adapters, info=_SessionInfo())
    initialize_connection(cast("psycopg.Connection[TupleRow]", session))
    return adapters


PORT_ADAPTERS: Final = _port_adapters()
"""The adapter map every runtime port dumps its binds under."""


def serialize(binds: Sequence[object]) -> Sequence[Buffer | None]:
    """The driver bytes ``binds`` become: production bind adaptation, then the
    dump of the one transformer each statement's cursor creates."""
    adapted = adapt_binds(binds)
    return Transformer(PORT_ADAPTERS).dump_sequence(adapted, [PyFormat.AUTO] * len(adapted))


class _Counter:
    __slots__ = ("reads", "roots", "statements")

    def __init__(self) -> None:
        self.reads = 0
        self.statements = 0
        self.roots = 0

    def reset(self) -> None:
        self.reads = self.statements = self.roots = 0

    def outcome(self, **extra: int) -> Outcome:
        return Outcome(statements=self.statements, reads=self.reads, roots=self.roots, **extra)


class _CountingPort(lowering_support.AcceptingPort):
    """The keyed-write port, counting what it answers and serializes."""

    __slots__ = ("counter",)

    def __init__(self, stored: Sequence[Mapping[str, object]]) -> None:
        super().__init__(stored)
        self.counter = _Counter()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        serialize(binds)
        self.counter.reads += 1
        return super().execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql
        serialize(binds)
        self.counter.statements += 1
        return 1


class _CompletingAcquisitionPort(acquisition_support.AcquisitionPort):
    """The predicate-acquisition port, completing the flush its window now
    includes: every statement's binds are serialized, and each write affects
    one row."""

    __slots__ = ("counter",)

    def __init__(self, stored: Callable[[int], Mapping[str, object]], rows: int) -> None:
        super().__init__(stored, rows)
        self.counter = _Counter()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        serialize(binds)
        self.counter.reads += 1
        return super().execute(sql, binds, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql
        serialize(binds)
        self.counter.statements += 1
        return 1


class _PagedReadPort(ConnectsAsItself):
    """``roots`` current acquisition milestones answered in key order, one
    page per limited statement whose binds are serialized. A page answers one
    lookahead row beyond its size, which the next page answers again;
    :meth:`reset` restarts delivery."""

    dialect: Dialect = POSTGRES
    __slots__ = ("_delivered", "_layout", "_roots", "counter")
    _layout: Layout

    def __init__(self, layout: Layout, roots: int) -> None:
        self._layout = layout
        self._roots = roots
        self._delivered = 0
        self.counter = _Counter()

    def reset(self) -> None:
        self._delivered = 0
        self.counter.reset()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        serialize(binds)
        self.counter.reads += 1
        limited = " limit " in sql
        size = cast("int", binds[-1]) if limited else self._roots
        taken = min(size, self._roots - self._delivered)
        first = self._delivered + 1
        self._delivered += taken - 1 if limited and taken == size else taken
        rows = (
            {**acquisition_support.stored_row(self._layout, key), "parallax_seek_0": key}
            for key in range(first, first + taken)
        )
        return projected_rows(sql, rows, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        raise AssertionError("a read workload writes nothing")

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
    ) -> TransactionOutcome[T]:
        del body, isolation
        raise AssertionError("a read workload opens no transaction")


class _ScriptedPort(ConnectsAsItself):
    """A port serializing every statement's binds, whose reads answer
    :attr:`answer`, which the workload sets to the stored state each read
    observes, and whose writes affect one row."""

    dialect: Dialect = POSTGRES
    __slots__ = ("answer", "counter")

    def __init__(self) -> None:
        self.answer: tuple[Mapping[str, object], ...] = ()
        self.counter = _Counter()

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        serialize(binds)
        self.counter.reads += 1
        return projected_rows(
            sql, (copy.deepcopy(dict(row)) for row in self.answer), document_reads
        )

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql
        serialize(binds)
        self.counter.statements += 1
        return 1

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        return [
            self.execute(statement.sql, statement.binds, statement.document_reads)
            for statement in statements
        ]

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: str | None = None,
    ) -> TransactionOutcome[T]:
        del isolation
        return body_outcome(cast("DatabaseConnection", self), body)


def _day(offset: int) -> dt.datetime:
    return _ORIGIN + offset * _DAY


def _serving(model: DomainModel) -> ServingModel:
    return ServingModel(prepare_model(model, edition=_EDITION))


@contextmanager
def _keyed_driver(
    case: lowering_support.Case, stored: Sequence[Mapping[str, object]]
) -> Generator[Driver]:
    port = _CountingPort(stored)
    with lowering_support.database(case, port) as handle:

        def run(stopwatch: Stopwatch) -> Outcome:
            port.counter.reset()
            lowering_support.write(handle, case, opened=stopwatch.start, closed=stopwatch.stop)
            return port.counter.outcome()

        yield Driver(run, port.counter.outcome)


def _gapped(stored: Mapping[str, object]) -> tuple[dict[str, object], ...]:
    """``stored`` as three intervals around the interior window, each followed
    by a gap but the last: [Jan, Apr), [May, Jul), and [Aug, infinity)."""
    months = ((1, 4), (5, 7), (8, None))
    return tuple(
        {
            **stored,
            "from_z": dt.datetime(2026, start, 1, tzinfo=dt.UTC),
            "thru_z": INFINITY if end is None else dt.datetime(2026, end, 1, tzinfo=dt.UTC),
        }
        for start, end in months
    )


@contextmanager
def _predicate_driver(cell: FlowCell) -> Generator[Driver]:
    case = acquisition_support.case_named(f"acquisition.rows-{_PREDICATE_TARGETS}.{cell.layout}")
    port = _CompletingAcquisitionPort(case.stored, case.rows)
    entity = cast("Any", case.entity)
    with Database(
        port.open(), _serving(case.model), clock=FixedClock(acquisition_support.INSTANT)
    ) as root:
        handle = root.using_database_login()

        def body(tx: Transaction, stopwatch: Stopwatch) -> None:
            stopwatch.start()
            window = {
                "valid_from": acquisition_support.INTERIOR_FROM,
                "until": acquisition_support.INTERIOR_UNTIL,
            }
            if cell.interface == "wire":
                tx.wire.update_where(case.target, case.changes, **window)
            else:
                tx.update_where(
                    entity.where(entity.id >= 1),
                    entity.title.set(acquisition_support.ASSIGNED_TITLE),
                    **window,
                )

        def run(stopwatch: Stopwatch) -> Outcome:
            port.counter.reset()
            handle.transact(lambda tx: body(tx, stopwatch), concurrency="optimistic")
            stopwatch.stop()
            return port.counter.outcome()

        yield Driver(run, port.counter.outcome)


def _read_query(cell: FlowCell) -> object:
    entity = cast(
        "Any",
        acquisition_support.AcquisitionColumns
        if cell.layout == "columns"
        else acquisition_support.AcquisitionDocument,
    )
    if cell.interface == "typed":
        return entity.where(entity.id >= 1).as_of(valid_time=LATEST, tx_time=LATEST)
    name = entity.identity.canonical
    return {
        "target": name,
        "predicate": {"greaterThanEquals": {"attr": f"{name}.id", "value": 1}},
        "temporal": {"valid-time": {"asOf": "latest"}, "transaction-time": {"asOf": "latest"}},
    }


def _delivery(database: ScopedDatabase, cell: FlowCell) -> Callable[[], int]:
    query = cast("Any", _read_query(cell))
    view: Any = database.wire if cell.interface == "wire" else database
    if cell.flow == "read-eager":
        return lambda: len(view.find(query).results())

    def streamed() -> int:
        with view.stream(query, batch_size=_PAGE_SIZE) as stream:
            return sum(1 for _root in stream)

    return streamed


@contextmanager
def _read_driver(cell: FlowCell) -> Generator[Driver]:
    port = _PagedReadPort(cell.layout, _READ_ROOTS)
    capacity = 0 if cell.mode == "preparation-inclusive" else DEFAULT_READ_PLAN_CACHE_CAPACITY
    with Database(
        port.open(), _serving(acquisition_support.MODEL), read_plan_cache_capacity=capacity
    ) as root:
        deliver = _delivery(root.using_database_login(), cell)
        if cell.mode == "reused-execution":
            deliver()

        def run(stopwatch: Stopwatch) -> Outcome:
            port.reset()
            stopwatch.start()
            port.counter.roots = deliver()
            stopwatch.stop()
            return port.counter.outcome()

        yield Driver(run, port.counter.outcome)


def _flow_driver(cell: FlowCell) -> AbstractContextManager[Driver]:
    if cell.flow == "predicate":
        return _predicate_driver(cell)
    if cell.flow in ("read-eager", "read-stream"):
        return _read_driver(cell)
    case_family = {
        "source-keyed": "interior",
        "target-patch": "target-patch",
        "target-replace": "target-replace",
    }[cell.flow]
    case = lowering_support.case_named(f"bitemporal.{case_family}.{cell.layout}.{cell.interface}")
    stored = cast("Mapping[str, object]", case.stored)
    rows = _gapped(stored) if cell.flow == "target-replace" else (stored,)
    return _keyed_driver(case, rows)


def _instance(key: int, label: str) -> Entity:
    return lowering_support.BiColumns(
        id=key,
        title=f"title-{label}",
        address=lowering_support.Address(
            city=f"city-{label}", geo=lowering_support.Geo(country="NO")
        ),
        tags=(lowering_support.Tag(label=f"tag-{label}"),),
    )


def _milestone(
    key: int, start: dt.datetime, end: object, label: str, opened: dt.datetime
) -> dict[str, object]:
    return {
        "id": key,
        "title": f"title-{label}",
        "address": {"city": f"city-{label}", "geo": {"country": "NO"}},
        "tags": [{"label": f"tag-{label}"}],
        "from_z": start,
        "thru_z": end,
        "in_z": opened,
        "out_z": INFINITY,
    }


@contextmanager
def _replacement_driver(size: int) -> Generator[Driver]:
    stored = tuple(
        _milestone(_TARGET_KEY, _day(4 * j), _day(4 * j + 3), "before", lowering_support.TX_START)
        for j in range(size // 2)
    )
    port = _CountingPort(stored)
    replacements = tuple(_instance(_TARGET_KEY, f"replacement-{i}") for i in range(size))
    with Database(
        port.open(), _serving(lowering_support.MODEL), clock=FixedClock(lowering_support.INSTANT)
    ) as root:
        handle = root.using_database_login()

        def body(tx: Transaction, stopwatch: Stopwatch) -> None:
            stopwatch.start()
            for index, instance in enumerate(replacements):
                tx.replace(
                    instance,
                    valid_from=_day(2 * index),
                    until=_day(2 * index + 2),
                    if_tx_start=lowering_support.TX_START,
                )

        def run(stopwatch: Stopwatch) -> Outcome:
            port.counter.reset()
            handle.transact(lambda tx: body(tx, stopwatch))
            stopwatch.stop()
            return port.counter.outcome()

        yield Driver(run, port.counter.outcome)


class _Abandoned(Exception):
    """Raised after a window so its transaction rolls back unflushed."""


@dataclass(slots=True)
class _Insertion:
    """One insertion of :data:`_KEY` over ``[origin, day(size))``, stored and
    split into ``size`` tagged rows, and the port answering its reads."""

    tx: Transaction
    port: _ScriptedPort
    size: int
    rows: tuple[dict[str, object], ...] = ()

    def _observed(self, answer: Mapping[str, object], pin: dt.datetime) -> Entity:
        self.port.answer = (answer,)
        entity = lowering_support.BiColumns
        query = entity.where(entity.id == _KEY).as_of(valid_time=pin, tx_time=LATEST)
        return cast("Entity", self.tx.find(query).result())

    def supersede(self) -> None:
        """Insert and store the object from :data:`_PREVIOUS_ANCHOR`, then
        remove all of it by a pending termination: the insertion :meth:`split`
        makes next is admitted by judging that removal against the stored
        insertion's removal window, and the flush storing it moves the
        record's retained anchor to the origin."""
        tx, size = self.tx, self.size
        tx.insert(_instance(_KEY, "previous"), valid_from=_PREVIOUS_ANCHOR, until=_day(size))
        previous = _milestone(
            _KEY, _PREVIOUS_ANCHOR, _day(size), "previous", lowering_support.INSTANT
        )
        tx.terminate(self._observed(previous, _PREVIOUS_ANCHOR))

    def split(self) -> None:
        """Insert and store the object, then reassign every even row of
        ``[origin, day(size))`` by a bounded update of its own, each from a
        source pinned at that row's start, so the next flush stores ``size``
        rows, each continuing the insertion."""
        tx, size = self.tx, self.size
        tx.insert(_instance(_KEY, "inserted"), valid_from=_ORIGIN, until=_day(size))
        inserted = _milestone(_KEY, _ORIGIN, _day(size), "inserted", lowering_support.INSTANT)
        sources = [self._observed(inserted, _day(2 * index)) for index in range(size // 2)]
        for index, source in enumerate(sources):
            row = 2 * index
            tx.update(cast("Any", source).edit(title=f"title-{row}"), until=_day(row + 1))
        self.rows = tuple(
            {
                **inserted,
                "title": f"title-{row}" if row % 2 == 0 else inserted["title"],
                "from_z": _day(row),
                "thru_z": _day(row + 1),
            }
            for row in range(size)
        )

    def source(self, row: int) -> Entity:
        """A source read inside stored row ``row``; the read flushes whatever
        is pending first."""
        return self._observed(self.rows[row], _day(row))

    def terminate(self, row: int, source: Entity) -> None:
        self.tx.terminate(source, until=_day(row + 1))

    def reinsert(self) -> bool:
        """Whether a reinsertion of the object is admitted, rather than refused
        as a repeat of the insertion still stored."""
        try:
            self.tx.insert(_instance(_KEY, "reinserted"), valid_from=_ORIGIN)
        except KeyedWriteValueError as refused:
            if refused.code != "write-value-already-stored":
                raise
            return False
        return True

    def refusals(self, stopwatch: Stopwatch) -> int:
        stopwatch.start()
        refused = sum(not self.reinsert() for _ in range(_REFUSALS_PER_WINDOW))
        stopwatch.stop()
        return refused


def _barrier(tx: Transaction, index: int) -> None:
    """A readless predicate write, which keeps the writes after it in a later
    barrier region."""
    entity = cast("Any", lowering_support.PlainColumns)
    tx.update_where(entity.where(entity.id == 1), entity.title.set(f"barrier-{index}"))


def _destruction(insertion: _Insertion, stopwatch: Stopwatch) -> Outcome:
    insertion.split()
    size = insertion.size
    order = [(index * _STRIDE) % size for index in range(size)]
    sources = [insertion.source(row) for row in order]
    for index, (row, source) in enumerate(zip(order, sources, strict=True)):
        insertion.terminate(row, source)
        _barrier(insertion.tx, index)
    stopwatch.start()
    admitted = insertion.reinsert()
    stopwatch.stop()
    return insertion.port.counter.outcome(admitted=int(admitted))


def _removal(insertion: _Insertion, stopwatch: Stopwatch) -> Outcome:
    insertion.supersede()
    insertion.split()
    insertion.terminate(0, insertion.source(0))
    refused = insertion.refusals(stopwatch)
    insertion.terminate(1, insertion.source(1))
    refused += insertion.refusals(stopwatch)
    return insertion.port.counter.outcome(refused=refused)


_ALGORITHM_RUNS: Final[Mapping[Algorithm, Callable[[_Insertion, Stopwatch], Outcome]]] = {
    "destruction-merge": _destruction,
    "removal-window": _removal,
}


@contextmanager
def _insertion_driver(cell: AlgorithmCell) -> Generator[Driver]:
    port = _ScriptedPort()
    scenario = _ALGORITHM_RUNS[cell.algorithm]
    with Database(
        port.open(), _serving(lowering_support.MODEL), clock=FixedClock(lowering_support.INSTANT)
    ) as root:
        handle = root.using_database_login()

        def body(tx: Transaction, stopwatch: Stopwatch, answer: list[Outcome]) -> None:
            answer.append(scenario(_Insertion(tx, port, cell.size), stopwatch))
            raise _Abandoned

        def run(stopwatch: Stopwatch) -> Outcome:
            port.counter.reset()
            answer: list[Outcome] = []
            try:
                handle.transact(lambda tx: body(tx, stopwatch, answer))
            except ExecutionFailure as failure:
                if not isinstance(failure.cause, _Abandoned):
                    raise
            (outcome,) = answer
            return outcome

        yield Driver(run, port.counter.outcome)


def driver(cell: Cell) -> AbstractContextManager[Driver]:
    """A context manager composing ``cell``'s workload outside every window
    and yielding its :class:`Driver`."""
    if isinstance(cell, FlowCell):
        return _flow_driver(cell)
    if cell.algorithm == "replacement-gaps":
        return _replacement_driver(cell.size)
    return _insertion_driver(cell)


@dataclass(frozen=True, slots=True)
class Reading:
    """One cell's measured samples, in microseconds per run, and the outcome
    every run reported."""

    cell: Cell
    samples_us: tuple[float, ...]
    windows: int
    outcome: Outcome


def _sampled(run: Callable[[Stopwatch], Outcome], expected: Outcome) -> tuple[Stopwatch, Outcome]:
    gc.collect()
    stopwatch = Stopwatch()
    outcome = run(stopwatch)
    if outcome != expected:
        raise RuntimeError(f"the run reported {outcome}, expected {expected}")
    if stopwatch.windows == 0:
        raise RuntimeError("the run timed no window")
    return stopwatch, outcome


def measure(cell: Cell, *, warmups: int, measured: int) -> Reading:
    """``warmups`` untimed runs and then ``measured`` timed runs of ``cell``,
    each preceded by a collection outside its window, every run checked
    against :func:`expected_outcome`."""
    if warmups < 0 or measured <= 0:
        raise ValueError("warmups must be non-negative and measured must be positive")
    expected = expected_outcome(cell)
    with driver(cell) as workload:
        for _ in range(warmups):
            _sampled(workload.run, expected)
        timed = [_sampled(workload.run, expected) for _ in range(measured)]
    windows = {stopwatch.windows for stopwatch, _outcome in timed}
    if len(windows) != 1:
        raise RuntimeError(f"runs timed differing window counts: {sorted(windows)}")
    return Reading(
        cell,
        tuple(stopwatch.elapsed_ns / 1_000 for stopwatch, _outcome in timed),
        windows.pop(),
        expected,
    )


def support_digest() -> str:
    """The SHA-256 digest of this module and every workload source it reuses."""
    digest = hashlib.sha256()
    digest.update(Path(__file__).read_bytes())
    digest.update(b"\0")
    digest.update(lowering_support.write_lowering_digest().encode("utf-8"))
    return digest.hexdigest()
