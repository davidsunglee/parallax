"""The predicate-flush workloads: one Bitemporal Wire ``amendUntil`` predicate
through the public ``tx.wire.amend_where`` verb, from the caller's documents to
the commit, over provider-free rows, under both storage layouts.

The verb selects every object by the row current at its ``valid_from`` and
buffers the group; the pre-commit flush then reads, batch by batch, the coverage
each object's window reaches past that row, settles each object, lowers and
binds its statements, and the commit ends the window. The port answers the
selection with each object's starting row and a coverage read with the later
rows of the objects whose keys it binds, composing each row when the statement
runs and keeping none.

``reaching`` objects end their starting row inside the window and hold one
later row there, in more objects than one batch settles; ``unchanged`` objects
hold the assigned title on both, so every milestone is kept by its guard; and
``wide`` is one object whose window reaches many later rows. A ``covered``
object's starting row runs to the open bound, so the flush reads nothing for
it. A reading's retained checkpoint is sampled when the
first write naming the last object executes: what is still held then of the
batches before it.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final, Literal, cast

from parallax.conformance.scripted_clock import FixedClock
from parallax.core import Entity
from parallax.core.base import INFINITY
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.snapshot import Database, ScopedDatabase, Transaction
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_rows
from tests.unit._predicate_acquisition_support import (
    ASSIGNED_TITLE,
    INSTANT,
    INTERIOR_FROM,
    INTERIOR_UNTIL,
    MODEL,
    TX_START,
    VALID_START,
    AcquisitionColumns,
    AcquisitionDocument,
)

__all__ = ["CASES", "Case", "Checkpoint", "FlushPort", "case_named", "database", "flush"]

type Layout = Literal["columns", "document"]
type Shape = Literal["covered", "reaching", "unchanged", "wide"]
type Checkpoint = Callable[[], None]

SPLIT: Final = dt.datetime(2026, 4, 1, tzinfo=dt.UTC)
"""Where a reaching object's starting row ends and its later rows begin,
inside the window."""

_ENTITIES: Final[Mapping[Layout, type[Entity]]] = {
    "columns": AcquisitionColumns,
    "document": AcquisitionDocument,
}


@dataclass(frozen=True, slots=True)
class Case:
    """One flush: how many objects its predicate selects, how many later rows
    each object's window reaches past its starting row, and whether every row
    already holds the assigned title."""

    name: str
    layout: Layout
    shape: Shape
    objects: int
    later: int

    @property
    def entity(self) -> type[Entity]:
        return _ENTITIES[self.layout]

    @property
    def equal(self) -> bool:
        return self.shape == "unchanged"

    @property
    def units(self) -> int:
        """The rows the window reaches, which every per-unit reading divides by."""
        return self.objects * (1 + self.later)


CASES: Final[tuple[Case, ...]] = (
    Case("predicate-flush.reaching.objects-128.columns", "columns", "reaching", 128, 1),
    Case("predicate-flush.reaching.objects-128.document", "document", "reaching", 128, 1),
    Case("predicate-flush.unchanged.objects-128.document", "document", "unchanged", 128, 1),
    Case("predicate-flush.wide.history-128.document", "document", "wide", 1, 128),
)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"{name!r} is not a predicate-flush case: {[case.name for case in CASES]}")


def _members(case: Case, key: int, piece: int) -> dict[str, object]:
    return {
        "title": ASSIGNED_TITLE if case.equal else f"title-{key:08d}-{piece}",
        "address": {"city": f"city-{key:08d}", "geo": {"country": "NO"}},
        "tags": [{"label": f"tag-{key:08d}-a"}, {"label": f"tag-{key:08d}-b"}],
    }


def _bounds(case: Case, piece: int) -> tuple[dt.datetime, object]:
    """The Valid Time of an object's ``piece``-th row: its starting row first,
    then each later row in turn, the last one open."""
    if not case.later:
        return VALID_START, INFINITY
    if piece == 0:
        return VALID_START, SPLIT
    start = SPLIT + dt.timedelta(hours=piece - 1)
    return start, INFINITY if piece == case.later else start + dt.timedelta(hours=1)


def stored_row(case: Case, key: int, piece: int) -> dict[str, object]:
    """One current row as the driver answers it, keyed by physical column."""
    start, end = _bounds(case, piece)
    bounds = {"from_z": start, "thru_z": end, "in_z": TX_START, "out_z": INFINITY}
    members = _members(case, key, piece)
    if case.layout == "document":
        return {"id": key, **bounds, "payload": members}
    return {"id": key, **members, **bounds}


class FlushPort(ConnectsAsItself):
    """A port whose selection answers every object's starting row and whose
    coverage reads answer the later rows of the objects they bind, each row
    composed when its statement runs; every write affects one row, and the
    transaction boundary is the body's own outcome. ``reached`` runs when the
    first write binding the last object executes."""

    dialect: Dialect = POSTGRES
    __slots__ = ("_case", "_last_seen", "reached")
    _case: Case
    _last_seen: bool
    reached: Checkpoint | None

    def __init__(self, case: Case) -> None:
        self._case = case
        self._last_seen = False
        self.reached = None

    def _rows(self, sql: str, binds: Sequence[object]) -> Iterator[Mapping[str, object]]:
        case = self._case
        if "from_z <= " in sql or "thru_z = " in sql:
            for key in range(1, case.objects + 1):
                yield stored_row(case, key, 0)
            return
        for key in _keys(binds):
            for piece in range(1, case.later + 1):
                yield stored_row(case, key, piece)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        return projected_rows(sql, self._rows(sql, binds), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql
        self._observe(binds)
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
        self._last_seen = False
        return body_outcome(cast("DatabaseConnection", self), body)

    def _observe(self, binds: Sequence[object]) -> None:
        reached = self.reached
        if reached is None or self._last_seen or self._case.objects not in _keys(binds):
            return
        self._last_seen = True
        reached()


def _keys(binds: Sequence[object]) -> list[int]:
    """The object keys a statement binds: its only integer binds."""
    return [bind for bind in binds if isinstance(bind, int) and not isinstance(bind, bool)]


@contextmanager
def database(case: Case) -> Generator[tuple[ScopedDatabase, FlushPort]]:
    """A connected handle over ``case``'s port, composed outside every window."""
    port = FlushPort(case)
    with Database(port.open(), MODEL, clock=FixedClock(INSTANT)) as root:
        yield root.using_database_login(), port


def flush(
    handle: ScopedDatabase,
    case: Case,
    *,
    opened: Checkpoint | None = None,
) -> None:
    """Select, buffer, flush, and commit ``case``'s Wire predicate write;
    ``opened`` runs immediately before the public verb."""
    entity = case.entity.identity.canonical
    target = {
        "entity": entity,
        "predicate": {"greaterThanEquals": {"path": f"{entity}.id", "value": 1}},
    }

    def body(transaction: Transaction) -> None:
        if opened is not None:
            opened()
        transaction.wire.amend_where(
            target, {"title": ASSIGNED_TITLE}, valid_from=INTERIOR_FROM, until=INTERIOR_UNTIL
        )

    handle.transact(body, concurrency="optimistic")
