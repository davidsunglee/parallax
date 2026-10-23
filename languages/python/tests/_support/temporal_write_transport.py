"""Public temporal writes over freshly seeded histories: the history each one
leaves, and how its statements cross the port, both calculated from the
workload's own definition rather than from anything production settles.

A cell is one workload at one size over one or more objects, on a connection
that holds the transport the server offers, holds none, or binds narrowly. Its
writes close every seeded milestone the window reaches and open the rows the
window leaves, so the cell's realization follows from the realization contract
alone (`m-execution` *Flush execution*): a run of two or more contiguous closes
is presented in ordered invocations of at most :data:`STATEMENT_CAP` statements
wherever the connection holds ordered write transport, a close that would be
its run's only one runs alone, and a run of contiguous openings is inserted at
most :data:`ENTRY_CAP` rows, and no more than the bind limit admits, to a
statement. Each write reaches milestones its transaction never read, so the
flush reads their coverage first (`m-unit-work` *Shared coverage
acquisition*): consecutive writes of one Entity share one read per span of at
most :data:`SPAN_WRITES`, after which all of them are ready and execute as one
Write Group, every close before every opening; a write of another Entity
between them ends the span, and each such write reads and executes alone. A
:class:`CountingConnection` forwarding the acquired connection keeps the
:class:`PortTally` the realization is compared with.

Nothing here opens a database.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any, Final, Literal, NamedTuple, cast

from parallax.core.base import INFINITY

if TYPE_CHECKING:
    from parallax.core.db_port import (
        AccessMode,
        DatabaseConnection,
        DocumentReadOrdinals,
        IsolationLevel,
        PipelineStatement,
        Row,
        TransactionOutcome,
    )
    from parallax.core.dialect import Dialect

__all__ = [
    "AMENDED_AT",
    "AMOUNT",
    "CELLS",
    "ENTRY_CAP",
    "NARROW_BIND_LIMIT",
    "REPLACED_LABEL",
    "SEEDED_AT",
    "SPAN_WRITES",
    "STATEMENT_CAP",
    "Cell",
    "ConnectionKind",
    "CountingConnection",
    "HistoryRow",
    "PortTally",
    "Realization",
    "Workload",
    "expected_flush_calls",
    "expected_history",
    "expected_realization",
    "object_key",
    "ordered_history",
    "seeded_history",
    "window",
]

type Workload = Literal["keyed-amend", "target-replace", "collection-amend", "interleaved-amend"]
"""An interleaved amendment alternates its objects between the keyed Entity
and another one storing a document, each amended as a keyed amendment is."""
type ConnectionKind = Literal["shipped", "unordered", "narrow"]
"""The acquired connection as the server offers it, without ordered write
transport, or reporting a bind limit of :data:`NARROW_BIND_LIMIT`."""

STATEMENT_CAP: Final = 64
"""The most statements one ordered write transport invocation presents."""
ENTRY_CAP: Final = 64
"""The most openings one multi-row insert carries."""
SPAN_WRITES: Final = 32
"""The most consecutive deferred writes one shared coverage read serves."""
NARROW_BIND_LIMIT: Final = 21
"""A bind limit admitting three keyed openings to an insert and every close."""
_INSERTED_COLUMNS: Final[dict[Workload, int]] = {"keyed-amend": 7}
"""The Columns one keyed opening binds: its key, label, amount, and the four
axis ends."""


@dataclass(frozen=True, slots=True, order=True)
class Cell:
    workload: Workload
    size: int
    objects: int = 1
    connection: ConnectionKind = "shipped"

    @property
    def id(self) -> str:
        objects = "" if self.objects == 1 else f"x{self.objects}"
        connection = "" if self.connection == "shipped" else f"-{self.connection}"
        return f"{self.workload}-{self.size}{objects}{connection}"


CELLS: Final[tuple[Cell, ...]] = (
    Cell("keyed-amend", 1),
    Cell("keyed-amend", 64),
    Cell("keyed-amend", 128),
    Cell("target-replace", 1),
    Cell("target-replace", 64),
    Cell("collection-amend", 64),
    Cell("keyed-amend", 3, 33),
    Cell("keyed-amend", 70, 3),
    Cell("keyed-amend", 3, 33, "unordered"),
    Cell("keyed-amend", 3, 33, "narrow"),
    Cell("target-replace", 4, 32),
    Cell("collection-amend", 4, 8),
    Cell("interleaved-amend", 3, 4),
)
"""Small and wide ranges and one past both caps; the collection cell carries
large, empty, duplicate-preserving, and nested collections. The several-object
cells share coverage reads: a full span and one past it, a few objects each
past both caps, the full span without ordered transport and with a narrow bind
limit, a target span, a collection span, and alternating Entities that share
nothing."""


# --------------------------------------------------------------------------- #
# The port tally and the forwarding connection that keeps it.
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class PortTally:
    """What one transaction asked of the port, as fixed scalars.

    ``standalone_non_insert_statements`` counts writes other than inserts
    executed alone, outside ordered write transport, ``inserts`` insert
    statements and ``inserted_rows`` the rows they carried, and ``ordered``
    ordered write transport invocations and ``ordered_statements`` the
    statements they presented; each ``widest_*`` is the most one statement or
    invocation carried.
    """

    reads: int = 0
    standalone_non_insert_statements: int = 0
    inserts: int = 0
    inserted_rows: int = 0
    widest_insert: int = 0
    ordered: int = 0
    ordered_statements: int = 0
    widest_ordered: int = 0

    def realization(self) -> Realization:
        return Realization(
            self.standalone_non_insert_statements,
            self.ordered,
            self.ordered_statements,
            self.widest_ordered,
            self.inserts,
            self.inserted_rows,
            self.widest_insert,
        )

    @property
    def logical_writes(self) -> int:
        """The Planned Steps the statements carried, however they were grouped."""
        return self.standalone_non_insert_statements + self.ordered_statements + self.inserted_rows


def _rows_inserted(sql: str) -> int:
    return sql.count("), (") + 1


class CountingConnection:
    """A forwarding connection keeping ``tally``.

    It has ordered write transport exactly where the connection it forwards to
    does, through a callable of its own stored once, unless ``kind`` withholds
    it, and reports its dialect with :data:`NARROW_BIND_LIMIT` where ``kind``
    narrows it; the connection a transaction hands its body is forwarded
    through another one of the same kind keeping the same tally.
    """

    __slots__ = ("_dialect", "_inner", "_kind", "_ordered", "_tally")

    def __init__(
        self, inner: DatabaseConnection, tally: PortTally, kind: ConnectionKind = "shipped"
    ) -> None:
        self._inner = inner
        self._tally = tally
        self._kind: ConnectionKind = kind
        self._ordered: Callable[[Sequence[Any]], Any] | None = (
            None
            if inner.ordered_write_transport is None or kind == "unordered"
            else self._ordered_write
        )
        self._dialect = (
            replace(inner.dialect, max_bind_parameters=NARROW_BIND_LIMIT)
            if kind == "narrow"
            else inner.dialect
        )

    @property
    def dialect(self) -> Dialect:
        return self._dialect

    def execute(
        self, sql: str, binds: Sequence[object], document_reads: Sequence[DocumentReadOrdinals] = ()
    ) -> list[Row]:
        self._tally.reads += 1
        return self._inner.execute(sql, binds, document_reads)

    def execute_pipeline(self, statements: Sequence[PipelineStatement]) -> list[list[Row]]:
        self._tally.reads += len(statements)
        return self._inner.execute_pipeline(statements)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        tally = self._tally
        if sql.startswith("insert"):
            rows = _rows_inserted(sql)
            tally.inserts += 1
            tally.inserted_rows += rows
            tally.widest_insert = max(tally.widest_insert, rows)
        else:
            tally.standalone_non_insert_statements += 1
        return self._inner.execute_write(sql, binds)

    @property
    def ordered_write_transport(self) -> Callable[[Sequence[Any]], Any] | None:
        return self._ordered

    def _ordered_write(self, statements: Sequence[Any]) -> Any:
        transport = cast("Callable[[Sequence[Any]], Any]", self._inner.ordered_write_transport)
        tally = self._tally
        tally.ordered += 1
        tally.ordered_statements += len(statements)
        tally.widest_ordered = max(tally.widest_ordered, len(statements))
        return transport(statements)

    def transaction[T](
        self,
        body: Callable[[DatabaseConnection], T],
        *,
        isolation: IsolationLevel | None = None,
        access_mode: AccessMode | None = None,
    ) -> TransactionOutcome[T]:
        tally = self._tally
        kind = self._kind

        def forwarded(connection: DatabaseConnection) -> T:
            return body(cast("DatabaseConnection", CountingConnection(connection, tally, kind)))

        return self._inner.transaction(forwarded, isolation=isolation, access_mode=access_mode)


# --------------------------------------------------------------------------- #
# The realization each cell takes.
# --------------------------------------------------------------------------- #


class Realization(NamedTuple):
    """How a transaction's writes crossed the port: non-insert statements run
    alone, ordered invocations with the statements they presented and the
    widest of them, and insert statements with the rows they carried and the
    widest of them."""

    standalone_non_insert_statements: int
    ordered: int
    ordered_statements: int
    widest_ordered: int
    inserts: int
    inserted_rows: int
    widest_insert: int


def _closes(closes: int, *, ordered: bool) -> tuple[int, int, int, int]:
    """One Write Group's run of ``closes``: the closes run alone, the
    invocations, the statements they present, and the widest invocation."""
    if not ordered:
        return closes, 0, 0, 0
    invocations, rest = divmod(closes, STATEMENT_CAP)
    alone = rest if rest == 1 else 0
    invocations += rest >= 2
    presented = closes - alone
    return alone, invocations, presented, min(presented, STATEMENT_CAP)


def _groups(cell: Cell) -> list[int]:
    """How many of ``cell``'s objects each Write Group its flush executes
    holds: alternating Entities each alone, otherwise every span's objects
    together."""
    if cell.workload == "interleaved-amend":
        return [1] * cell.objects
    spans, rest = divmod(cell.objects, SPAN_WRITES)
    return [SPAN_WRITES] * spans + ([rest] if rest else [])


def _openings(cell: Cell) -> int:
    """One object's openings: its head, the rows the window leaves, and its
    tail; an amendment one row per milestone, a replacement one row over all of
    them."""
    return 3 if cell.workload == "target-replace" else cell.size + 2


def _entries_per_insert(cell: Cell) -> int:
    if cell.connection != "narrow":
        return ENTRY_CAP
    return min(ENTRY_CAP, NARROW_BIND_LIMIT // _INSERTED_COLUMNS[cell.workload])


def _group_realization(cell: Cell, objects: int, *, ordered: bool) -> Realization:
    alone, invocations, presented, widest = _closes(objects * cell.size, ordered=ordered)
    openings = objects * _openings(cell)
    per_insert = _entries_per_insert(cell)
    return Realization(
        alone,
        invocations,
        presented,
        widest,
        -(-openings // per_insert),
        openings,
        min(openings, per_insert),
    )


def expected_realization(cell: Cell, *, ordered: bool) -> Realization:
    """What ``cell``'s one transaction presents to a connection acquired from
    a server that does, or does not, offer ``ordered`` write transport.

    Each Write Group closes every seeded milestone its objects' windows reach,
    in one contiguous run, and then opens every object's rows in one run of
    openings.
    """
    ordered = ordered and cell.connection != "unordered"
    groups = [_group_realization(cell, objects, ordered=ordered) for objects in _groups(cell)]
    return Realization(
        sum(group.standalone_non_insert_statements for group in groups),
        sum(group.ordered for group in groups),
        sum(group.ordered_statements for group in groups),
        max(group.widest_ordered for group in groups),
        sum(group.inserts for group in groups),
        sum(group.inserted_rows for group in groups),
        max(group.widest_insert for group in groups),
    )


def expected_flush_calls(cell: Cell) -> list[tuple[str, int]]:
    """The Database Calls of ``cell``'s one flush, each run of statements
    collapsed into one ``("write", count)``: before each Write Group, the
    shared coverage read returning every milestone its objects' windows reach
    beyond the one their transaction already holds, and then the group's
    closes and insert statements. A window inside the one milestone held reads
    nothing."""
    calls: list[tuple[str, int]] = []
    per_insert = _entries_per_insert(cell)
    for objects in _groups(cell):
        if cell.size > 1:
            calls.append(("read", objects * (cell.size - 1)))
        calls.append(("write", objects * cell.size + -(-objects * _openings(cell) // per_insert)))
    return calls


# --------------------------------------------------------------------------- #
# Workload definitions and their independently calculated history.
# --------------------------------------------------------------------------- #

EPOCH: Final = dt.datetime(2020, 1, 1, tzinfo=dt.UTC)
SEEDED_AT: Final = dt.datetime(2019, 6, 1, tzinfo=dt.UTC)
AMENDED_AT: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
AMOUNT: Final = 999
REPLACED_LABEL: Final = "replaced"
_MILESTONE: Final = dt.timedelta(days=30)
_HEAD: Final = dt.timedelta(days=10)
_TAIL: Final = dt.timedelta(days=20)


class HistoryRow(NamedTuple):
    key: int
    valid_from: dt.datetime
    valid_to: object
    tx_from: dt.datetime
    tx_to: object
    label: str
    amount: int


def milestone_start(index: int) -> dt.datetime:
    return EPOCH + _MILESTONE * index


def window(size: int) -> tuple[dt.datetime, dt.datetime]:
    """Where a range over ``size`` milestones starts and ends: inside its
    first milestone, and inside its last."""
    milestones = 1 if size < 1 else size
    return milestone_start(0) + _HEAD, milestone_start(milestones - 1) + _TAIL


def object_key(sample: int) -> int:
    """The key of the one object sample ``sample`` writes."""
    return sample + 1


def _label(workload: Workload, key: int, index: int) -> str:
    return f"{workload[0]}{key}-{index}"


def seeded_history(workload: Workload, size: int, sample: int) -> list[HistoryRow]:
    """The milestones sample ``sample``'s object starts with: adjacent, each
    holding a label of its own, so no two of them can ever merge."""
    key = object_key(sample)
    rows: list[HistoryRow] = []
    for index in range(size):
        end: object = INFINITY if index == size - 1 else milestone_start(index + 1)
        rows.append(
            HistoryRow(
                key,
                milestone_start(index),
                end,
                SEEDED_AT,
                INFINITY,
                _label(workload, key, index),
                index,
            )
        )
    return rows


def expected_history(workload: Workload, size: int, sample: int) -> list[HistoryRow]:
    """Sample ``sample``'s whole history once its write committed: every
    seeded milestone the window reaches closed at the write's instant, and the
    current rows calculated piece by piece from the window."""
    seeded = seeded_history(workload, size, sample)
    start, end = window(size)
    closed = [row._replace(tx_to=AMENDED_AT) for row in seeded]
    first, last = seeded[0], seeded[-1]
    opened = [first._replace(valid_to=start, tx_from=AMENDED_AT)]
    if workload == "target-replace":
        key = object_key(sample)
        opened.append(HistoryRow(key, start, end, AMENDED_AT, INFINITY, REPLACED_LABEL, AMOUNT))
    else:
        for row in seeded:
            piece_from = max(row.valid_from, start)
            piece_to = end if row.valid_to is INFINITY else min(_finite(row.valid_to), end)
            opened.append(
                row._replace(
                    valid_from=piece_from, valid_to=piece_to, tx_from=AMENDED_AT, amount=AMOUNT
                )
            )
    opened.append(last._replace(valid_from=end, tx_from=AMENDED_AT))
    return sorted([*closed, *opened], key=_order)


def _finite(value: object) -> dt.datetime:
    assert isinstance(value, dt.datetime)
    return value


def _order(row: HistoryRow) -> tuple[int, dt.datetime, dt.datetime]:
    return row.key, row.tx_from, row.valid_from


def ordered_history(rows: Iterable[HistoryRow]) -> list[HistoryRow]:
    return sorted(rows, key=_order)
