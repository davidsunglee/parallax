"""The keyed-write workloads measured without database I/O, from Typed or Wire
input through the public keyed verbs, the pre-commit flush, and the driver's own
bind serialization.

One class-backed model carries the categorical matrix — Transaction-Time-Only,
non-temporal, and Bitemporal Entities under both storage layouts, each with a
One Value Object nesting another One and a Many — beside the geometry Entities
:mod:`tests.unit._structural_geometry_support` declares. The geometry levels
open a lineage; the changed-ancestor levels succeed one, changing a single leaf
of a wide root occurrence so the cost of replacing that occurrence is read
against its declared width. The leaf-type inserts open a lineage of each type
:mod:`tests.unit._leaf_type_support` declares, over that module's own model,
through Typed and Wire input; the width level's Typed geometry insert is their
String control, and a Wire String insert is declared beside them. Every case
names its model, ingress, layout, mutation, authored values, and the stored row
it revises.

Each run is one transaction. A case that revises a row first reads it through
production (``tx.find`` or ``tx.wire.find``), because a keyed write is licensed
only by evidence a read of this store retained, and a Typed case edits what the
read published. The window then runs from the public verb — ``tx.insert``,
``tx.update``, ``tx.update_until``, or their ``tx.wire`` peers — until
``transact`` returns: preparation, effective-change classification, buffering,
the pre-commit flush's planning, settlement, and SQL lowering, and the commit.
The read and what the caller authors against it are outside it.

The window ends where the driver would hand bytes to the socket: the
provider-free port crosses each statement's binds through the production
PostgreSQL bind adaptation and psycopg's own transformer dump, which is the
serialization ``cursor.execute`` performs, and reports one affected row.
Database execution and network time are outside it.

Beside the lowering matrix, one public Wire insert is measured through the
shipped ``tx.wire.insert`` over a provider-free port: a nested, polymorphic
Create Payload opens a row of a table-per-hierarchy family whose members nest a
One inside a One beside a Many, and the window is the verb itself, from the
payload arriving to the frozen node it answers, with the commit that follows
outside it. The family is a model of its own, so its preparation prices the
family variant beside the structural model's preparation rather than inside it.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

import datetime as dt
import hashlib
from collections.abc import Callable, Generator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, cast

from psycopg import postgres
from psycopg.abc import Buffer
from psycopg.adapt import PyFormat, Transformer

from parallax.conformance.scripted_clock import FixedClock
from parallax.conformance.workloads import GEOMETRY_LEVELS, leaf_type_digest, structural_digest
from parallax.core import (
    AbstractRoot,
    Attr,
    Bitemporal,
    ConcreteSubtype,
    Document,
    DomainModel,
    Entity,
    TablePerHierarchy,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.base import detach_json_container
from parallax.core.db_port import (
    DatabaseConnection,
    DocumentReadOrdinals,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.object_query import LATEST
from parallax.core.storage_layout import view as storage_layout_view
from parallax.core.unit_work import KeyedMutation
from parallax.core.unit_work.instructions import coerce_typed_row
from parallax.postgres._connection import adapt_binds
from parallax.snapshot.handle import (
    Database,
    ScopedDatabase,
    Transaction,
    WireEntity,
)
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_rows
from tests.unit import _leaf_type_support as leaf_support
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _structural_geometry_support as geometry_support

__all__ = [
    "ANCESTOR_KEY",
    "CASES",
    "CATALOG",
    "ENTITY_CLASSES",
    "FAMILY_ENTITY_CLASSES",
    "FAMILY_MODEL",
    "MODEL",
    "RESPONSE_CASES",
    "AcceptingPort",
    "Case",
    "Executed",
    "Ingress",
    "Layout",
    "ResponseCase",
    "case_named",
    "database",
    "insert_response",
    "lowered",
    "response_case_named",
    "response_database",
    "serialize",
    "write",
    "write_lowering_digest",
]

type Layout = Literal["columns", "document"]
type Ingress = Literal["typed", "wire"]
type Checkpoint = Callable[[], None]

_NAMESPACE: Final = "write.lowering"

TX_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
VALID_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
INSTANT: Final = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)
"""The Transaction Instant every write flushes at: later than every stored
milestone's opening, so each close and successor is a genuine step forward."""
INTERIOR_FROM: Final = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
INTERIOR_UNTIL: Final = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
"""A Valid-Time window strictly inside the predecessor's open interval, so a
Bitemporal ``updateUntil`` produces a close, a carried head, a changed middle,
and a carried tail."""


class Geo(ValueObject):
    country: Attr[str]


class Address(ValueObject):
    city: Attr[str]
    geo: Attr[Geo]


class Tag(ValueObject):
    label: Attr[str]


class TxColumns(TxTemporal, table="write_lowering_tx_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class TxDocument(
    TxTemporal,
    table="write_lowering_tx_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class PlainColumns(Entity, table="write_lowering_plain_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class PlainDocument(
    Entity,
    table="write_lowering_plain_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class BiColumns(Bitemporal, table="write_lowering_bi_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class BiDocument(
    Bitemporal,
    table="write_lowering_bi_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class Pet(
    Entity,
    table="write_lowering_pet",
    namespace=_NAMESPACE,
    inheritance=AbstractRoot(TablePerHierarchy(tag_column="kind")),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class Dog(Pet, namespace=_NAMESPACE, inheritance=ConcreteSubtype(tag_value="dog")):
    bark_volume: Attr[int | None]


class Cat(Pet, namespace=_NAMESPACE, inheritance=ConcreteSubtype(tag_value="cat")):
    indoor: Attr[bool | None]


FAMILY_ENTITY_CLASSES: Final[tuple[type[Entity], ...]] = (Pet, Dog, Cat)
"""The table-per-hierarchy family the public insert opens a row of, and the
whole of the model its preparation is priced over."""

FAMILY_MODEL: Final = DomainModel(*FAMILY_ENTITY_CLASSES)

_CATEGORICAL: Final[Mapping[tuple[str, Layout], type[Entity]]] = {
    ("txtime", "columns"): TxColumns,
    ("txtime", "document"): TxDocument,
    ("plain", "columns"): PlainColumns,
    ("plain", "document"): PlainDocument,
    ("bitemporal", "columns"): BiColumns,
    ("bitemporal", "document"): BiDocument,
}

ENTITY_CLASSES: Final[tuple[type[Entity], ...]] = (
    *_CATEGORICAL.values(),
    *geometry_support.ENTITY_CLASSES,
    *acquisition_support.ENTITY_CLASSES,
)
"""Every Entity the write model prepares: the categorical matrix, the geometry
families, and the predicate-acquisition families, so one model-preparation
checkpoint prices the whole structural workload."""

MODEL: Final = DomainModel(*ENTITY_CLASSES)
CATALOG: Final = CatalogedModel(model_of(MODEL))
LAYOUTS: Final[tuple[Layout, ...]] = ("columns", "document")
INGRESSES: Final[tuple[Ingress, ...]] = ("typed", "wire")
ANCESTOR_KEY: Final = 1
LEAF_FAMILY: Final = "leaf"
LEAF_KEY: Final = 1


@dataclass(frozen=True, slots=True)
class Case:
    """One keyed write, what its caller authors, and the stored row it revises.

    ``model`` is the domain model the case's handle is connected over.
    ``instance`` is the Typed value a Typed insert opens, held as its caller
    holds it. ``changes`` is what any other case authors: a Typed update's
    ``edit`` keywords, a Wire update's changes document with its identity
    omitted, or a Wire insert's Create Payload — composed outside the window
    exactly as a caller's arrives. ``stored`` is the milestone the case's read
    answers, keyed by physical column as the driver answers it, and ``None`` for
    an insert, which reads nothing. ``statements`` is how many statements the
    flush executes.
    """

    name: str
    family: str
    entity: type[Entity]
    ingress: Ingress
    layout: Layout
    mutation: KeyedMutation
    instance: Entity | None
    changes: Mapping[str, object]
    stored: Mapping[str, object] | None
    statements: int
    model: DomainModel
    bounded: bool = False


_CODEC: Final = EntityRowCodec(CATALOG)


def _value(cls: type[Entity], key: int, label: str) -> Entity:
    return cls(
        id=key,
        title=f"title-{label}",
        address=Address(city=f"city-{label}", geo=Geo(country=f"country-{label}")),
        tags=(Tag(label=f"tag-{label}-a"), Tag(label=f"tag-{label}-b")),
    )


def _wire_row(value: Entity) -> dict[str, object]:
    """``value``'s complete row in canonical Wire spellings, as a fresh mapping."""
    entity = CATALOG.meta.entity(type(value).identity)
    assert entity is not None
    row = coerce_typed_row(_CODEC.full_row(value), CATALOG.meta, entity)
    return cast("dict[str, object]", detach_json_container(row))


def _document_placement(cls: type[Entity]) -> tuple[str, tuple[str, ...]]:
    """The Structured Column ``cls`` stores its document residents in, and their
    names in residency order."""
    view = storage_layout_view(CATALOG.meta).entity(cls.identity)
    residents = None if view is None else view.document_residents
    assert residents is not None, cls
    (column,) = {placement.slot.column.name for placement in residents.placements}
    return column, tuple(member.name for member in residents.shape.members)


def _stored_row(value: Entity, layout: Layout) -> dict[str, object]:
    """The current milestone ``value`` states, keyed by physical column as the
    driver answers it."""
    row = _wire_row(value)
    if isinstance(value, Bitemporal):
        row.update(from_z=VALID_START, thru_z=OPEN_BOUND)
    if isinstance(value, Bitemporal | TxTemporal):
        row.update(in_z=TX_START, out_z=OPEN_BOUND)
    if layout == "document":
        column, members = _document_placement(type(value))
        row[column] = {name: row.pop(name) for name in members}
    return row


def _authored(ingress: Ingress, mutation: KeyedMutation, value: Entity) -> Mapping[str, object]:
    """What a caller states for ``value``: a Wire insert's whole payload, or
    every member but the identity as an update's edit keywords or changes."""
    row = _wire_row(value)
    if mutation == "insert":
        return row if ingress == "wire" else {}
    del row["id"]
    if ingress == "wire":
        return row
    return {name: getattr(value, name) for name in row}


def _keyed_case(
    name: str,
    family: str,
    ingress: Ingress,
    layout: Layout,
    *,
    mutation: KeyedMutation,
    value: Entity,
    predecessor: Entity | None,
    statements: int,
    bounded: bool = False,
) -> Case:
    return Case(
        name,
        family,
        type(value),
        ingress,
        layout,
        mutation,
        value if mutation == "insert" and ingress == "typed" else None,
        _authored(ingress, mutation, value),
        None if predecessor is None else _stored_row(predecessor, layout),
        statements,
        MODEL,
        bounded,
    )


def _case(
    family: str,
    operation: str,
    layout: Layout,
    ingress: Ingress,
    *,
    mutation: KeyedMutation,
    key: int,
    label: str,
    predecessor: str | None,
    statements: int,
    bounded: bool = False,
) -> Case:
    cls = _CATEGORICAL[(family, layout)]
    return _keyed_case(
        f"{family}.{operation}.{layout}.{ingress}",
        family,
        ingress,
        layout,
        mutation=mutation,
        value=_value(cls, key, label),
        predecessor=None if predecessor is None else _value(cls, key, predecessor),
        statements=statements,
        bounded=bounded,
    )


def _categorical_cases() -> tuple[Case, ...]:
    cases: list[Case] = []
    for layout in LAYOUTS:
        for ingress in INGRESSES:
            cases.append(
                _case(
                    "txtime",
                    "opening",
                    layout,
                    ingress,
                    mutation="insert",
                    key=101,
                    label="opening",
                    predecessor=None,
                    statements=1,
                )
            )
            cases.append(
                _case(
                    "txtime",
                    "changed",
                    layout,
                    ingress,
                    mutation="update",
                    key=301,
                    label="after",
                    predecessor="before",
                    statements=2,
                )
            )
            cases.append(
                _case(
                    "txtime",
                    "unchanged",
                    layout,
                    ingress,
                    mutation="update",
                    key=501,
                    label="same",
                    predecessor="same",
                    statements=0,
                )
            )
            cases.append(
                _case(
                    "plain",
                    "changed",
                    layout,
                    ingress,
                    mutation="update",
                    key=701,
                    label="after",
                    predecessor="before",
                    statements=1,
                )
            )
            cases.append(
                _case(
                    "bitemporal",
                    "interior",
                    layout,
                    ingress,
                    mutation="updateUntil",
                    key=901,
                    label="middle",
                    predecessor="before",
                    statements=4,
                    bounded=True,
                )
            )
    return tuple(cases)


def _geometry_cases() -> tuple[Case, ...]:
    return tuple(
        _keyed_case(
            f"geometry.{level.id}.{layout}.typed",
            f"geometry-{level.family}",
            "typed",
            layout,
            mutation="insert",
            value=geometry_support.instance(level, layout, 1),
            predecessor=None,
            statements=1,
        )
        for level in GEOMETRY_LEVELS
        for layout in geometry_support.LAYOUTS
    )


def _ancestor_cases() -> tuple[Case, ...]:
    """One changed successor per ancestor level and layout.

    The successor restates every member and changes one leaf of the root
    occurrence, so the write closes its milestone and opens a row whose
    Structured Column production composes from the retained predecessor
    document.
    """
    return tuple(
        _keyed_case(
            f"ancestor.{level.id}.{layout}.typed",
            f"ancestor-{level.family}",
            "typed",
            layout,
            mutation="update",
            value=geometry_support.successor_instance(level, layout, ANCESTOR_KEY, changed=True),
            predecessor=geometry_support.successor_instance(
                level, layout, ANCESTOR_KEY, changed=False
            ),
            statements=2,
        )
        for level in geometry_support.ANCESTOR_LEVELS
        for layout in geometry_support.LAYOUTS
    )


def _leaf_cases() -> tuple[Case, ...]:
    """One insert per leaf type, layout, and ingress over the leaf-type model:
    Typed and Wire for each measured type, Wire alone for the String control,
    whose Typed insert is the width level's geometry case."""
    return tuple(
        Case(
            f"{LEAF_FAMILY}.{leaf.id}.{layout}.{ingress}",
            LEAF_FAMILY,
            leaf_support.entity_class(leaf, layout),
            ingress,
            layout,
            "insert",
            leaf_support.instance(leaf, layout, LEAF_KEY) if ingress == "typed" else None,
            leaf_support.wire_row(leaf, LEAF_KEY) if ingress == "wire" else {},
            None,
            1,
            leaf_support.MODEL,
        )
        for leaf in leaf_support.WIRE_INSERTED_TYPES
        for layout in LAYOUTS
        for ingress in (INGRESSES if leaf in leaf_support.MEASURED_TYPES else ("wire",))
    )


CASES: Final[tuple[Case, ...]] = (
    *_categorical_cases(),
    *_geometry_cases(),
    *_ancestor_cases(),
    *_leaf_cases(),
)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"{name!r} is not a write-lowering case: {[case.name for case in CASES]}")


@dataclass(frozen=True, slots=True)
class ResponseCase:
    """One public Wire insert: the concrete Entity the row opens under and the
    Create Payload in Wire spellings, composed outside the window exactly as a
    caller's payload arrives."""

    name: str
    entity: type[Entity]
    payload: Mapping[str, object]


RESPONSE_CASES: Final[tuple[ResponseCase, ...]] = (
    ResponseCase(
        "response.insert.family.wire",
        Dog,
        {
            "id": 1101,
            "title": "title-response",
            "address": {"city": "city-response", "geo": {"country": "country-response"}},
            "tags": [{"label": "tag-response-a"}, {"label": "tag-response-b"}],
            "barkVolume": 3,
        },
    ),
)
"""The public insert cases: one nested, polymorphic payload whose answered node
carries a One inside a One, a Many, and the family variant."""


def response_case_named(name: str) -> ResponseCase:
    for case in RESPONSE_CASES:
        if case.name == name:
            return case
    raise KeyError(
        f"{name!r} is not a public insert case: {[case.name for case in RESPONSE_CASES]}"
    )


def serialize(binds: Sequence[object]) -> Sequence[Buffer | None]:
    """The driver bytes ``binds`` become: production bind adaptation followed by
    the transformer dump ``cursor.execute`` performs."""
    adapted = adapt_binds(binds)
    transformer = Transformer(postgres.adapters)
    return transformer.dump_sequence(adapted, [PyFormat.AUTO] * len(adapted))


class AcceptingPort(ConnectsAsItself):
    """A provider-free port that answers every read with ``stored``, serializes
    every DML statement's binds as the driver would, and counts it as one
    affected row, committing every transaction.

    The stored rows are copied per statement, so nothing a read answers is
    shared with the fixture or with an earlier read.
    """

    dialect: Dialect = POSTGRES
    __slots__ = ("_stored",)
    _stored: tuple[Mapping[str, object], ...]

    def __init__(self, stored: Sequence[Mapping[str, object]] = ()) -> None:
        self._stored = tuple(stored)

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        del binds
        rows = (cast("Mapping[str, object]", detach_json_container(row)) for row in self._stored)
        return projected_rows(sql, rows, document_reads)

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        del sql
        serialize(binds)
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


@contextmanager
def response_database(case: ResponseCase) -> Generator[ScopedDatabase]:
    """A login-scoped handle over the family model ``case`` opens a row of,
    composed outside every window and closed after the last one."""
    root = Database.connect(AcceptingPort(), FAMILY_MODEL)
    try:
        yield root.using_database_login()
    finally:
        root.close()


def insert_response(
    handle: ScopedDatabase,
    case: ResponseCase,
    *,
    opened: Callable[[], None] | None = None,
    closed: Callable[[], None] | None = None,
) -> WireEntity:
    """The public insert window: ``opened`` marks the moment before
    ``tx.wire.insert`` receives the payload and ``closed`` the moment the frozen
    node it answers is held, with the commit that flushes the row outside both."""

    def body(tx: Transaction) -> WireEntity:
        if opened is not None:
            opened()
        node = tx.wire.insert(case.entity.identity.name, case.payload)
        if closed is not None:
            closed()
        return node

    return handle.transact(body)


@contextmanager
def database(case: Case, port: AcceptingPort | None = None) -> Generator[ScopedDatabase]:
    """A login-scoped handle over ``case``'s model and stored row, composed
    outside every window, flushing at :data:`INSTANT`."""
    stored = () if case.stored is None else (case.stored,)
    with Database(
        (AcceptingPort(stored) if port is None else port).open(),
        case.model,
        clock=FixedClock(INSTANT),
    ) as root:
        yield root.using_database_login()


def _source(tx: Transaction, case: Case) -> object:
    """What the verb revises: the node the case's read publishes, edited for a
    Typed case; nothing for an insert, which revises no row."""
    if case.stored is None:
        return None
    entity = cast("Any", case.entity)
    query = entity.where(entity.id == case.stored["id"])
    if issubclass(case.entity, Bitemporal):
        query = query.as_of(valid_time=LATEST)
    if case.ingress == "wire":
        return tx.wire.find(query).result()
    return tx.find(query).result().edit(**case.changes)


def _buffer(tx: Transaction, case: Case, source: object) -> None:
    """Buffer ``case``'s keyed write through its public verb."""
    window = {"valid_from": INTERIOR_FROM, "until": INTERIOR_UNTIL} if case.bounded else {}
    if case.ingress == "typed":
        if case.mutation == "insert":
            tx.insert(cast("Entity", case.instance))
        elif case.mutation == "updateUntil":
            tx.update_until(cast("Entity", source), **window)
        else:
            tx.update(cast("Entity", source))
        return
    if case.mutation == "insert":
        tx.wire.insert(case.entity.identity.name, case.changes)
    elif case.mutation == "updateUntil":
        tx.wire.update_until(cast("WireEntity", source), case.changes, **window)
    else:
        tx.wire.update(cast("WireEntity", source), case.changes)


def write(
    handle: ScopedDatabase,
    case: Case,
    *,
    opened: Checkpoint | None = None,
    buffered: Checkpoint | None = None,
    closed: Checkpoint | None = None,
) -> None:
    """Run ``case`` as one committed transaction.

    ``opened`` runs after the read, immediately before the verb; ``buffered``
    immediately after the verb has buffered, still inside the transaction body;
    and ``closed`` once ``transact`` has returned, its flush and commit done. A
    reading marks its window with ``opened`` and ``closed``, and takes what the
    verb kept between ``opened`` and ``buffered``.
    """

    def body(tx: Transaction) -> None:
        source = _source(tx, case)
        if opened is not None:
            opened()
        _buffer(tx, case, source)
        if buffered is not None:
            buffered()

    handle.transact(body)
    if closed is not None:
        closed()


@dataclass(frozen=True, slots=True)
class Executed:
    """One statement the flush executed, as the port received it, beside the
    bytes the driver dumps its binds to."""

    sql: str
    binds: tuple[object, ...]
    dumped: Sequence[Buffer | None]


class _RecordingPort(AcceptingPort):
    __slots__ = ("executed",)
    executed: list[Executed]

    def __init__(self, stored: Sequence[Mapping[str, object]]) -> None:
        super().__init__(stored)
        self.executed = []

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        self.executed.append(Executed(sql, tuple(binds), serialize(binds)))
        return 1


def lowered(case: Case) -> tuple[Executed, ...]:
    """Every statement one run of ``case`` executes, for a suite grading what
    the window produced."""
    port = _RecordingPort(() if case.stored is None else (case.stored,))
    with database(case, port) as handle:
        write(handle, case)
    return tuple(port.executed)


def write_lowering_digest() -> str:
    """The SHA-256 digest of every source this workload is defined by."""
    digest = hashlib.sha256()
    for module in (
        Path(__file__),
        Path(geometry_support.__file__),
        Path(acquisition_support.__file__),
        Path(leaf_support.__file__),
    ):
        digest.update(module.read_bytes())
        digest.update(b"\0")
    digest.update(structural_digest().encode("utf-8"))
    digest.update(leaf_type_digest().encode("utf-8"))
    return digest.hexdigest()
