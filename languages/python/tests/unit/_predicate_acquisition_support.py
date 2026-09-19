"""The predicate-acquisition companion workloads: one prepared Bitemporal
``updateUntil`` predicate resolved against provider-free rows, under both
storage layouts, through the production materializing predicate-write path.

The window opens with a prepared predicate instruction and a port whose
resolving read answers freshly composed rows, and closes once the Unit of Work
has buffered the Materialized Write Group: read planning and compilation, row
publication and materialization, per-row no-op selection, predecessor
ownership establishment, aligned column construction, and buffering are inside
it. Ingress preparation, JSON parsing, the flush, and driver serialization are
outside it, and the transaction is abandoned after the checkpoint so no flush
runs at all.

Every assignment is genuinely changed against every resolved row, so no-op
elimination retains them all. The port composes each row when the statement
runs and keeps none, and the Database is composed once per reading outside the
window, so what a retained checkpoint sees is what production kept.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from parallax.conformance.workloads import ACQUISITION_LEVELS, AcquisitionLevel
from parallax.core import Attr, Bitemporal, Document, DomainModel, Entity, ValueObject, attr
from parallax.core.base import INFINITY
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity._model import model_of
from parallax.core.object_query._fluent import mutation_selection
from parallax.core.unit_work import (
    FixedClock,
    PredicateSelection,
    PredicateWrite,
    WriteAssignment,
    instructions,
)
from parallax.core.unit_work.instructions import PreparedPredicateWrite
from parallax.snapshot.handle import Database, ExecutionFailure, ScopedDatabase, Transaction
from parallax.snapshot.handle._transaction import buffer_prepared_predicate_write
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_rows

__all__ = [
    "ACQUISITION_LEVELS",
    "CASES",
    "ENTITY_CLASSES",
    "MODEL",
    "AcquisitionPort",
    "Case",
    "Checkpoint",
    "Layout",
    "acquire",
    "case_named",
    "database",
]

type Layout = Literal["columns", "document"]
type Checkpoint = Callable[[], None]

_NAMESPACE: Final = "predicate.acquisition"

TX_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
VALID_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
INSTANT: Final = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
INTERIOR_FROM: Final = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
INTERIOR_UNTIL: Final = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
ASSIGNED_TITLE: Final = "title-changed"


class Geo(ValueObject):
    country: Attr[str]


class Address(ValueObject):
    city: Attr[str]
    geo: Attr[Geo]


class Tag(ValueObject):
    label: Attr[str]


class AcquisitionColumns(Bitemporal, table="acquisition_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class AcquisitionDocument(
    Bitemporal,
    table="acquisition_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


ENTITY_CLASSES: Final[tuple[type[Entity], ...]] = (AcquisitionColumns, AcquisitionDocument)
MODEL: Final = DomainModel(*ENTITY_CLASSES)
LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
_ENTITIES: Final[Mapping[Layout, type[Entity]]] = {
    "columns": AcquisitionColumns,
    "document": AcquisitionDocument,
}


@dataclass(frozen=True, slots=True)
class Case:
    """One acquisition family level: the prepared predicate and the rows it resolves."""

    name: str
    layout: Layout
    entity: type[Entity]
    level: AcquisitionLevel
    prepared: PreparedPredicateWrite

    @property
    def rows(self) -> int:
        return self.level.rows


def _prepared(cls: type[Entity]) -> PreparedPredicateWrite:
    """The interior ``updateUntil`` over every row, prepared exactly as the
    typed ``update_until_where`` verb prepares it."""
    key = cast("Any", cls).id
    title = cast("Any", cls).title
    selection = mutation_selection(cls.where(key >= 1))
    assignment = title.set(ASSIGNED_TITLE)
    instruction = PredicateWrite(
        "updateUntil",
        PredicateSelection(selection.target.canonical, selection.predicate),
        (WriteAssignment(str(assignment.attr), assignment.value),),
        INTERIOR_FROM,
        INTERIOR_UNTIL,
    )
    prepared = instructions.prepare_typed_write(instruction, model_of(MODEL))
    assert isinstance(prepared, PreparedPredicateWrite)
    return prepared


CASES: Final[tuple[Case, ...]] = tuple(
    Case(f"acquisition.{level.id}.{layout}", layout, _ENTITIES[layout], level, _prepared(cls))
    for layout in LAYOUTS
    for cls in (_ENTITIES[layout],)
    for level in ACQUISITION_LEVELS
)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"{name!r} is not an acquisition case: {[case.name for case in CASES]}")


def _members(key: int) -> dict[str, object]:
    return {
        "title": f"title-{key:08d}",
        "address": {"city": f"city-{key:08d}", "geo": {"country": "NO"}},
        "tags": [{"label": f"tag-{key:08d}-a"}, {"label": f"tag-{key:08d}-b"}],
    }


def stored_row(layout: Layout, key: int) -> dict[str, object]:
    """One current milestone as the driver answers it, keyed by physical column."""
    bounds: dict[str, object] = {
        "from_z": VALID_START,
        "thru_z": INFINITY,
        "in_z": TX_START,
        "out_z": INFINITY,
    }
    if layout == "document":
        return {"id": key, **bounds, "payload": _members(key)}
    return {"id": key, **_members(key), **bounds}


class AcquisitionPort(ConnectsAsItself):
    """A port whose resolving read answers ``rows`` freshly composed milestones
    and whose transaction boundary is the body's own outcome."""

    dialect: Dialect = POSTGRES
    __slots__ = ("_layout", "_rows")
    _layout: Layout
    _rows: int

    def __init__(self, layout: Layout, rows: int) -> None:
        self._layout = layout
        self._rows = rows

    def rows(self) -> Iterator[Mapping[str, object]]:
        for offset in range(self._rows):
            yield stored_row(self._layout, 1 + offset)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del binds
        return projected_rows(sql, self.rows(), document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql, binds
        raise AssertionError("an acquisition window ends before any flush")

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


class _Abandoned(Exception):
    """Raised after the checkpoint so the transaction rolls back unflushed."""


@contextmanager
def database(case: Case) -> Generator[ScopedDatabase]:
    """A connected handle over ``case``'s port, composed outside every window."""
    with Database(
        AcquisitionPort(case.layout, case.rows).open(), MODEL, clock=FixedClock(INSTANT)
    ) as root:
        yield root.using_database_login()


def acquire(
    handle: ScopedDatabase,
    case: Case,
    *,
    opened: Checkpoint | None = None,
    closed: Checkpoint | None = None,
) -> None:
    """Resolve and buffer ``case``'s prepared predicate, then abandon the
    transaction.

    ``opened`` runs immediately before the acquisition and ``closed``
    immediately after the group is buffered, both inside the transaction body
    and before any flush could run; a reading marks its window with them.
    """

    def body(transaction: Transaction) -> None:
        if opened is not None:
            opened()
        buffer_prepared_predicate_write(transaction, case.prepared)
        if closed is not None:
            closed()
        raise _Abandoned

    try:
        handle.transact(body, concurrency="optimistic")
    except ExecutionFailure as failure:
        if isinstance(failure.cause, _Abandoned):
            return
        raise
    raise AssertionError("an acquisition window is abandoned before its flush")
