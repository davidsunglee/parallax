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
``tx.amend``, a bounded ``tx.amend``, or their ``tx.wire`` peers — until
``transact`` returns: preparation, buffering, the pre-commit flush's planning,
settlement, and SQL lowering, and the commit. The read and what the caller
authors against it are outside it. The unchanged cases author no member at all,
which is the amendment that changes nothing: a member restated at its stored value
is a literal assignment and writes like any other.

The target cases revise a row their transaction never read:
a Wire amendment (``tx.wire.amend_if``) or a Typed or Wire replacement
(``tx.replace_if``, ``tx.wire.replace_if``) states the key, the
Transaction-Time start its temporal caller last observed, and a Bitemporal
target's interior window, under the default Optimistic strategy. Their window
opens at the verb, with nothing read before it, so it contains the one read the
target makes: the coverage read its flush makes before it closes anything. The
port answers it with the stored row, composed per statement.
Every target assigns every writable member the values its observed twin
assigns, so the two lower to the same statements.

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

The cross-object flushes are keyed loops: one transaction reads many distinct
objects of one categorical Entity, amends each through its own public verb,
and commits, so its pre-commit flush plans and executes every amendment as
Write Groups rather than as one step the planner collapsed. The read, what the
caller authors, and admission all precede the flush. Production's planning and
step-execution seams are wrapped to mark two regions inside it: finalization,
ending at the finalized plan before anything executes, and each Write Group's
steps, with that group's completion between one region and the next. The
port these flushes write through offers ordered write transport, serializes
every statement it is presented on either path as the driver would, and counts
the statements, invocations, largest ordered invocation, and largest grouped
insert of one flush in constant space.

The deferred-span flushes amend Bitemporal objects past the milestone their
transaction read, so each amendment reaches milestones only the flush's shared
coverage reads acquire, and the writes each read makes ready execute as one
Write Group. Their port answers a read as of an instant with the milestones
current then, and a coverage read with the milestones its terms reach, and
counts the coverage reads too. A third region is marked inside these flushes:
each advance of the flush's scoped range binding, which prepares the span,
acquires coverage until the next write is ready, and binds the ready writes
into the group the next execution region runs. A requesting flush is the
read-dependency flush a later read causes, with every source still held, so it
captures the rows its writes leave for their sources; the others are the
concluding pre-commit flush, which captures nothing.

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
from parallax.core._execution._unit_work.instructions import coerce_typed_row
from parallax.core._execution._unit_work.ranges import RangeBindings
from parallax.core._execution._unit_work.write_planner import WritePlanner, WritePlanningRequest
from parallax.core._execution._write_step_executor import WriteStepExecutor
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.base import detach_json_container
from parallax.core.db_port import (
    CanonicalWriteStatement,
    DatabaseConnection,
    DocumentReadOrdinals,
    OrderedWriteResult,
    OrderedWriteResultComplete,
    OrderedWriteTransport,
    PipelineStatement,
    Row,
    TransactionOutcome,
)
from parallax.core.dialect import POSTGRES, Dialect
from parallax.core.entity import EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.execution_lifecycle._activity import FlushActivity
from parallax.core.storage_layout import view as storage_layout_view
from parallax.core.unit_work import KeyedMutation, TargetMutation
from parallax.core.write_plan.payload import PatchedDocument
from parallax.core.write_plan.plan import WriteGroup, WritePlan
from parallax.core.write_plan.steps import PlannedStep, PlannedTemporalRevision, WriteRow
from parallax.postgres._connection import adapt_binds
from parallax.snapshot import Database, ScopedDatabase, TxnContext, WireEntity
from tests._support.db_port import ConnectsAsItself, body_outcome, projected_rows
from tests.unit import _leaf_type_support as leaf_support
from tests.unit import _structural_geometry_support as geometry_support

__all__ = [
    "ANCESTOR_KEY",
    "CASES",
    "CATALOG",
    "CROSS_OBJECT_CASES",
    "CROSS_OBJECT_PREFIX",
    "DEFERRED_CASES",
    "ENTITY_CLASSES",
    "FAMILY_ENTITY_CLASSES",
    "FAMILY_MODEL",
    "MODEL",
    "RESPONSE_CASES",
    "AcceptingPort",
    "Case",
    "CrossObjectCase",
    "Executed",
    "FlushRegions",
    "FlushWork",
    "Ingress",
    "Layout",
    "OrderedAcceptingPort",
    "ResponseCase",
    "SpanAcceptingPort",
    "case_named",
    "cross_object_case_named",
    "database",
    "flush_database",
    "flush_objects",
    "flush_port",
    "insert_response",
    "lowered",
    "marked_flushes",
    "response_case_named",
    "response_database",
    "serialize",
    "unmarked",
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
)
"""Every Entity the write model prepares: the categorical matrix and the
geometry families, so one model-preparation checkpoint prices the whole
structural workload."""

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
    ``instance`` is the Typed value a Typed insert opens or a Typed replacement
    states, held as its caller holds it. ``changes`` is what any other case
    authors: a Typed update's ``edit`` keywords, a Wire update's changes
    document with its identity omitted, or a Wire insert's Create Payload, or a
    Wire target's document with its identity — composed outside the window
    exactly as a caller's arrives. ``stored`` is the milestone the case's read
    answers, keyed by physical column as the driver answers it, and ``None`` for
    an insert, which reads nothing; an ``addressed`` target reads nothing before
    its verb, and its stored row answers the reads the target itself makes
    inside the window. ``statements`` is how many Planned Steps the flush
    realizes; a grouped insert can realize several in one physical statement.
    """

    name: str
    family: str
    entity: type[Entity]
    ingress: Ingress
    layout: Layout
    mutation: KeyedMutation | TargetMutation
    instance: Entity | None
    changes: Mapping[str, object]
    stored: Mapping[str, object] | None
    statements: int
    model: DomainModel
    bounded: bool = False
    addressed: bool = False


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


def _authored(
    ingress: Ingress, mutation: KeyedMutation | TargetMutation, value: Entity, *, addressed: bool
) -> Mapping[str, object]:
    """What a caller states for ``value``: a Wire insert's or Wire target's
    whole document, identity included, or every member but the identity as an
    update's edit keywords or changes. A Typed insert or replacement states the
    instance itself."""
    row = _wire_row(value)
    if mutation == "insert" or addressed:
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
    mutation: KeyedMutation | TargetMutation,
    value: Entity,
    predecessor: Entity | None,
    statements: int,
    bounded: bool = False,
    expressed: bool = True,
    members: frozenset[str] | None = None,
    addressed: bool = False,
) -> Case:
    authored: Mapping[str, object] = (
        _authored(ingress, mutation, value, addressed=addressed) if expressed else {}
    )
    if members is not None:
        authored = {name: member for name, member in authored.items() if name in members}
    states_instance = mutation in ("insert", "replace", "replaceUntil") and ingress == "typed"
    return Case(
        name,
        family,
        type(value),
        ingress,
        layout,
        mutation,
        value if states_instance else None,
        authored,
        None if predecessor is None else _stored_row(predecessor, layout),
        statements,
        MODEL,
        bounded,
        addressed,
    )


def _case(
    family: str,
    operation: str,
    layout: Layout,
    ingress: Ingress,
    *,
    mutation: KeyedMutation | TargetMutation,
    key: int,
    label: str,
    predecessor: str | None,
    statements: int,
    bounded: bool = False,
    expressed: bool = True,
    addressed: bool = False,
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
        expressed=expressed,
        addressed=addressed,
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
                    mutation="amend",
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
                    mutation="amend",
                    key=501,
                    label="same",
                    predecessor="same",
                    statements=0,
                    expressed=False,
                )
            )
            cases.append(
                _case(
                    "plain",
                    "changed",
                    layout,
                    ingress,
                    mutation="amend",
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
                    mutation="amendUntil",
                    key=901,
                    label="middle",
                    predecessor="before",
                    statements=4,
                    bounded=True,
                )
            )
    return tuple(cases)


_TARGET_TWINS: Final[tuple[tuple[str, int, str, int, bool], ...]] = (
    ("txtime", 301, "after", 2, False),
    ("bitemporal", 901, "middle", 4, True),
)
"""Each target family's observed twin: its key, the label of the values it
assigns, its statement count, and whether it is bounded to the interior
window. The predecessor is always the twin's ``before`` row. The unversioned
``plain`` family has no revision a caller could state, so it has no target
write."""


def _target_cases() -> tuple[Case, ...]:
    """One Wire patch and one Typed and Wire replacement per categorical
    family and layout; a Typed target patch is no public verb."""
    cases: list[Case] = []
    for family, key, label, statements, bounded in _TARGET_TWINS:
        for layout in LAYOUTS:
            forms: tuple[tuple[str, TargetMutation, Ingress], ...] = (
                ("target-patch", "amendUntil" if bounded else "amend", "wire"),
                *(
                    ("target-replace", "replaceUntil" if bounded else "replace", ingress)
                    for ingress in INGRESSES
                ),
            )
            cases.extend(
                _case(
                    family,
                    operation,
                    layout,
                    ingress,
                    mutation=mutation,
                    key=key,
                    label=label,
                    predecessor="before",
                    statements=statements,
                    bounded=bounded,
                    addressed=True,
                )
                for operation, mutation, ingress in forms
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

    The successor assigns the root occurrence alone, with one leaf changed, so
    the write closes its milestone and opens a row whose Structured Column
    production composes from the retained predecessor document. Assignments are
    literal, so restating the other members would write them too.
    """
    return tuple(
        _keyed_case(
            f"ancestor.{level.id}.{layout}.typed",
            f"ancestor-{level.family}",
            "typed",
            layout,
            mutation="amend",
            value=geometry_support.successor_instance(level, layout, ANCESTOR_KEY, changed=True),
            predecessor=geometry_support.successor_instance(
                level, layout, ANCESTOR_KEY, changed=False
            ),
            statements=2,
            members=frozenset({geometry_support.CHANGED_OCCURRENCE}),
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
    *_target_cases(),
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


def _composed(value: object) -> object:
    """A fresh copy of a stored row's containers. The keyed-write pass
    observations count ``detach_json_container`` returns, and a target's reads
    fall inside the window, so the port composes its answers without it."""
    if isinstance(value, Mapping):
        return {key: _composed(item) for key, item in cast("Mapping[str, object]", value).items()}
    if isinstance(value, list | tuple):
        return [_composed(item) for item in cast("Sequence[object]", value)]
    return value


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
        rows = (cast("Mapping[str, object]", _composed(row)) for row in self._stored)
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
        access_mode: str | None = None,
    ) -> TransactionOutcome[T]:
        del isolation, access_mode
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

    def body(tx: TxnContext) -> WireEntity:
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


def _source(tx: TxnContext, case: Case) -> object:
    """What the verb revises: the node the case's read publishes, edited for a
    Typed case; nothing for an insert, which revises no row, or for a target,
    which addresses its row by key."""
    if case.stored is None or case.addressed:
        return None
    entity = cast("Any", case.entity)
    query = entity.where(entity.id == case.stored["id"])
    if issubclass(case.entity, Bitemporal):
        query = query.as_of(valid_time=INTERIOR_FROM)
    if case.ingress == "wire":
        return tx.wire.find(query).result()
    return tx.find(query).result().edit(**case.changes)


def _address(tx: TxnContext, case: Case) -> None:
    """Buffer ``case``'s target write through its public verb, conditioned on
    the stored milestone's Transaction-Time start. Each branch states its
    keywords literally, so the window holds the verb's own work and no
    argument assembly."""
    name = case.entity.identity.name
    if case.mutation in ("replace", "replaceUntil") and case.ingress == "typed":
        instance = cast("Entity", case.instance)
        if case.bounded:
            tx.replace_if(
                instance, tx_start=TX_START, valid_from=INTERIOR_FROM, until=INTERIOR_UNTIL
            )
        else:
            tx.replace_if(instance, tx_start=TX_START)
        return
    verb = tx.wire.replace_if if case.mutation in ("replace", "replaceUntil") else tx.wire.amend_if
    if case.bounded:
        verb(name, case.changes, tx_start=TX_START, valid_from=INTERIOR_FROM, until=INTERIOR_UNTIL)
    else:
        verb(name, case.changes, tx_start=TX_START)


def _buffer(tx: TxnContext, case: Case, source: object) -> None:
    """Buffer ``case``'s keyed write through its public verb."""
    if case.addressed:
        _address(tx, case)
        return
    if case.ingress == "typed":
        if case.mutation == "insert":
            tx.insert(cast("Entity", case.instance))
        elif case.mutation == "amendUntil":
            tx.amend(cast("Entity", source), until=INTERIOR_UNTIL)
        else:
            tx.amend(cast("Entity", source))
        return
    if case.mutation == "insert":
        tx.wire.insert(case.entity.identity.name, case.changes)
    elif case.mutation == "amendUntil":
        tx.wire.amend(cast("WireEntity", source), case.changes, until=INTERIOR_UNTIL)
    else:
        tx.wire.amend(cast("WireEntity", source), case.changes)


def write(
    handle: ScopedDatabase,
    case: Case,
    *,
    opened: Checkpoint | None = None,
    buffered: Checkpoint | None = None,
    closed: Checkpoint | None = None,
) -> None:
    """Run ``case`` as one committed transaction.

    ``opened`` runs immediately before the verb, after the read where the case
    makes one; ``buffered``
    immediately after the verb has buffered, still inside the transaction body;
    and ``closed`` once ``transact`` has returned, its flush and commit done. A
    reading marks its window with ``opened`` and ``closed``, and takes what the
    verb kept between ``opened`` and ``buffered``.
    """

    def body(tx: TxnContext) -> None:
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


CROSS_OBJECT_PREFIX: Final = "cross-object."


@dataclass(frozen=True, slots=True)
class FlushWork:
    """What one flush presented to its port: every statement, every call that
    presented one or more of them, the most statements one ordered invocation
    presented, and the most rows one insert statement wrote."""

    statements: int
    invocations: int
    largest_ordered_invocation: int
    largest_grouped_insert: int


@dataclass(frozen=True, slots=True)
class CrossObjectCase:
    """One flush of keyed amendments over distinct objects of one Entity.

    ``stored`` holds the milestones the transaction's reads answer, keyed by
    physical column as the driver answers them, and ``changes`` what the
    caller authors for each object, by key: a Typed case's ``edit`` keywords
    or a Wire case's changes document, composed outside every window as a
    caller's arrives. ``groups`` is how many settled writes each Write Group
    the flush executes holds, and ``work`` what executing them presents to the
    port.

    A deferred-span case also holds the ``acquired`` milestones only a
    coverage read answers. Its transaction reads its objects as of each of
    ``reads`` and amends every source it read from that instant until
    ``reach`` past it, and its flush reads coverage ``coverage_reads`` times;
    where ``requesting``, a later read causes that flush with every source
    still held.
    """

    name: str
    entity: type[Entity]
    ingress: Ingress
    layout: Layout
    bounded: bool
    stored: tuple[Mapping[str, object], ...]
    changes: Mapping[int, Mapping[str, object]]
    groups: tuple[int, ...]
    work: FlushWork
    acquired: tuple[Mapping[str, object], ...] = ()
    reads: tuple[dt.datetime, ...] = ()
    reach: dt.timedelta = dt.timedelta(0)
    coverage_reads: int = 0
    requesting: bool = False

    @property
    def objects(self) -> int:
        return len({row["id"] for row in self.stored})

    @property
    def deferred(self) -> bool:
        return self.coverage_reads > 0


def _cross_object_case(
    family: str,
    operation: str,
    layout: Layout,
    ingress: Ingress,
    *,
    first_key: int,
    label: str,
    groups: tuple[int, ...],
    work: FlushWork,
) -> CrossObjectCase:
    cls = _CATEGORICAL[(family, layout)]
    keys = range(first_key, first_key + sum(groups))
    mutation: KeyedMutation = "amendUntil" if family == "bitemporal" else "amend"
    return CrossObjectCase(
        f"{CROSS_OBJECT_PREFIX}{family}.{operation}-{len(keys)}.{layout}.{ingress}",
        cls,
        ingress,
        layout,
        mutation == "amendUntil",
        tuple(_stored_row(_value(cls, key, "before"), layout) for key in keys),
        {
            key: _authored(ingress, mutation, _value(cls, key, label), addressed=False)
            for key in keys
        },
        groups,
        work,
    )


_MILESTONE: Final = dt.timedelta(days=30)
_DAY: Final = dt.timedelta(days=1)
_AMENDED_TITLE: Final = "title-amended"


def _milestone(
    cls: type[Entity], layout: Layout, key: int, start: dt.datetime, end: object
) -> Mapping[str, object]:
    """Object ``key``'s milestone over ``[start, end)``, labelled by its start
    so no two milestones of one object state the same values."""
    row = _stored_row(_value(cls, key, f"{start:%Y%m%d}"), layout)
    row.update(from_z=start, thru_z=end)
    return row


def _deferred_changes(keys: range) -> dict[int, Mapping[str, object]]:
    """A new title for each object, its only change, so each amended piece
    keeps the values that set it apart from its neighbours and none merge."""
    return {key: {"title": _AMENDED_TITLE} for key in keys}


def _deferred_span_case(
    operation: str,
    layout: Layout,
    ingress: Ingress,
    *,
    first_key: int,
    objects: int,
    milestones: int,
    work: FlushWork,
    requesting: bool = False,
) -> CrossObjectCase:
    """``objects`` Bitemporal objects of ``milestones`` adjacent milestones
    each, the last open, read as of a day inside the first and amended until
    a day inside the last: each amendment closes every milestone, opens its
    head, an amended piece of each milestone, and its tail, and owes one
    window of the milestones after the first, which one shared coverage read
    acquires for all of them."""
    cls = _CATEGORICAL[("bitemporal", layout)]
    keys = range(first_key, first_key + objects)
    starts = [VALID_START + _MILESTONE * index for index in range(milestones)]
    ends: list[object] = [*starts[1:], OPEN_BOUND]
    history = {
        key: [
            _milestone(cls, layout, key, start, end)
            for start, end in zip(starts, ends, strict=True)
        ]
        for key in keys
    }
    read = VALID_START + 10 * _DAY
    return CrossObjectCase(
        f"{CROSS_OBJECT_PREFIX}bitemporal.{operation}-{objects}x{milestones}.{layout}.{ingress}",
        cls,
        ingress,
        layout,
        True,
        tuple(rows[0] for rows in history.values()),
        _deferred_changes(keys),
        (objects,),
        work,
        acquired=tuple(row for rows in history.values() for row in rows[1:]),
        reads=(read,),
        reach=starts[-1] + 20 * _DAY - read,
        coverage_reads=1,
        requesting=requesting,
    )


def _partial_successor_case(*, first_key: int) -> CrossObjectCase:
    """Two objects of 66 daily milestones, the last open, and one of two,
    each read as of the start of every other milestone and amended from each
    milestone read through the next, so every object owes a window per
    milestone pair: 33, 33, and 1. A coverage read carries at most 64
    windows, so the first reads all of the first object's and 31 of the
    second's, which leaves the second a partial successor; the first object
    runs alone before the second read, after which the other two run
    together."""
    cls = _CATEGORICAL[("bitemporal", "columns")]
    keys = range(first_key, first_key + 3)
    observed: list[Mapping[str, object]] = []
    acquired: list[Mapping[str, object]] = []
    for key, length in zip(keys, (66, 66, 2), strict=True):
        for index in range(length):
            start = VALID_START + _DAY * index
            end = OPEN_BOUND if index == length - 1 and length > 2 else start + _DAY
            (acquired if index % 2 else observed).append(
                _milestone(cls, "columns", key, start, end)
            )
    return CrossObjectCase(
        f"{CROSS_OBJECT_PREFIX}bitemporal.partial-3x66.columns.typed",
        cls,
        "typed",
        "columns",
        True,
        tuple(observed),
        _deferred_changes(keys),
        (1, 2),
        # Alone: 66 closes in two invocations, 67 openings in two inserts;
        # together: 68 closes in two, 69 openings in two.
        FlushWork(66 + 2 + 68 + 2, 2 + 2 + 2 + 2, 64, 64),
        acquired=tuple(acquired),
        reads=tuple(VALID_START + _DAY * index for index in range(0, 66, 2)),
        reach=2 * _DAY,
        coverage_reads=2,
    )


DEFERRED_CASES: Final[tuple[CrossObjectCase, ...]] = (
    # 128 closes in two invocations, 192 openings in three inserts.
    _deferred_span_case(
        "deferred",
        "columns",
        "typed",
        first_key=4001,
        objects=32,
        milestones=4,
        work=FlushWork(128 + 3, 2 + 3, 64, 64),
    ),
    # 384 closes in six invocations, 448 openings in seven inserts.
    _deferred_span_case(
        "deferred",
        "document",
        "wire",
        first_key=5001,
        objects=32,
        milestones=12,
        work=FlushWork(384 + 7, 6 + 7, 64, 64),
    ),
    _deferred_span_case(
        "requesting",
        "document",
        "wire",
        first_key=6001,
        objects=32,
        milestones=12,
        work=FlushWork(384 + 7, 6 + 7, 64, 64),
        requesting=True,
    ),
    # 1024 closes in 16 invocations, 1088 openings in 17 inserts.
    _deferred_span_case(
        "deferred",
        "columns",
        "typed",
        first_key=7001,
        objects=32,
        milestones=32,
        work=FlushWork(1024 + 17, 16 + 17, 64, 64),
    ),
    _partial_successor_case(first_key=8001),
)
"""Deferred spans of typical, large, and exceptional reach across 32 objects,
the large one under a concluding and a requesting flush, and a span whose
coverage takes two reads, one object running before the second."""


CROSS_OBJECT_CASES: Final[tuple[CrossObjectCase, ...]] = (
    _cross_object_case(
        "txtime",
        "changed",
        "columns",
        "typed",
        first_key=1001,
        label="after",
        groups=(64,),
        work=FlushWork(65, 2, 64, 64),
    ),
    _cross_object_case(
        "txtime",
        "changed",
        "columns",
        "typed",
        first_key=2001,
        label="after",
        groups=(64, 64, 2),
        work=FlushWork(133, 6, 64, 64),
    ),
    _cross_object_case(
        "bitemporal",
        "interior",
        "document",
        "wire",
        first_key=3001,
        label="middle",
        groups=(64,),
        work=FlushWork(67, 4, 64, 64),
    ),
    *DEFERRED_CASES,
)
"""Keyed amendments under the default Optimistic strategy: each Write Group's
closes share ordered invocations and its successors grouped inserts, and a
Bitemporal interior amendment opens a head, a changed middle, and a tail. The
deferred spans follow."""


def cross_object_case_named(name: str) -> CrossObjectCase:
    for case in CROSS_OBJECT_CASES:
        if case.name == name:
            return case
    raise KeyError(
        f"{name!r} is not a cross-object case: {[case.name for case in CROSS_OBJECT_CASES]}"
    )


def _inserted_rows(sql: str) -> int:
    return sql.count("), (") + 1 if sql.startswith("insert") else 0


class OrderedAcceptingPort(AcceptingPort):
    """An :class:`AcceptingPort` that also offers ordered write transport,
    converting each presented statement to the driver's SQL and serializing its
    binds as the PostgreSQL adapter does before queuing it, and confirming one
    affected row for each; it counts what one flush presents as
    :class:`FlushWork`, keeping nothing else of a statement."""

    __slots__ = (
        "_invocations",
        "_largest_insert",
        "_largest_ordered",
        "_statements",
        "_transport",
    )
    _statements: int
    _invocations: int
    _largest_ordered: int
    _largest_insert: int
    _transport: OrderedWriteTransport

    def __init__(self, stored: Sequence[Mapping[str, object]] = ()) -> None:
        super().__init__(stored)
        self._transport = self._ordered_writes
        self.reset()

    def reset(self) -> None:
        self._statements = self._invocations = 0
        self._largest_ordered = self._largest_insert = 0

    def work(self) -> FlushWork:
        return FlushWork(
            self._statements, self._invocations, self._largest_ordered, self._largest_insert
        )

    @property
    def ordered_write_transport(self) -> OrderedWriteTransport | None:
        return self._transport

    def execute_write(self, sql: str, binds: Sequence[object]) -> int:
        affected = super().execute_write(sql, binds)
        self._statements += 1
        self._invocations += 1
        self._largest_insert = max(self._largest_insert, _inserted_rows(sql))
        return affected

    def _ordered_writes(self, statements: Sequence[CanonicalWriteStatement]) -> OrderedWriteResult:
        for statement in statements:
            self.dialect.to_driver_sql(statement.sql).encode()
            serialize(statement.binds)
        presented = len(statements)
        self._statements += presented
        self._invocations += 1
        self._largest_ordered = max(self._largest_ordered, presented)
        return OrderedWriteResultComplete((1,) * presented)


class SpanAcceptingPort(OrderedAcceptingPort):
    """An :class:`OrderedAcceptingPort` over objects' whole histories: a read
    of a key range as of an instant answers the ``stored`` milestones current
    then, and a coverage read the ``acquired`` milestones its terms reach,
    each once, looked up by key so answering costs what the rows it returns
    do. A coverage read is the one naming a Valid-Time start strictly before
    a window's end; its binds name each term's key and then each of its
    windows' start and end. It counts the coverage reads of one flush beside
    its :class:`FlushWork`."""

    __slots__ = ("_acquired", "coverage_reads")
    _acquired: Mapping[object, tuple[Mapping[str, object], ...]]
    coverage_reads: int

    def __init__(
        self,
        stored: Sequence[Mapping[str, object]] = (),
        acquired: Sequence[Mapping[str, object]] = (),
    ) -> None:
        super().__init__(stored)
        by_key: dict[object, list[Mapping[str, object]]] = {}
        for row in acquired:
            by_key.setdefault(row["id"], []).append(row)
        self._acquired = {key: tuple(rows) for key, rows in by_key.items()}
        self.coverage_reads = 0

    def reset(self) -> None:
        super().reset()
        self.coverage_reads = 0

    def execute(
        self,
        sql: str,
        binds: Sequence[object],
        document_reads: Sequence[DocumentReadOrdinals] = (),
    ) -> list[Row]:
        if " t0.from_z < " in sql:
            self.coverage_reads += 1
            rows = _covered(self._acquired, binds)
        else:
            rows = _current(self._stored, binds)
        return projected_rows(
            sql, (cast("Mapping[str, object]", _composed(row)) for row in rows), document_reads
        )


def _ends(row: Mapping[str, object]) -> tuple[dt.datetime, object]:
    return cast("dt.datetime", row["from_z"]), row["thru_z"]


def _overlaps(row: Mapping[str, object], since: dt.datetime, until: object) -> bool:
    start, end = _ends(row)
    return (until is OPEN_BOUND or start < cast("dt.datetime", until)) and (
        end is OPEN_BOUND or cast("dt.datetime", end) > since
    )


def _current(
    rows: Sequence[Mapping[str, object]], binds: Sequence[object]
) -> list[Mapping[str, object]]:
    """The rows of keys ``first`` through ``last`` current as of ``instant``,
    the binds a key range read as of one instant names first."""
    first, last, instant = cast("tuple[int, int, dt.datetime]", tuple(binds[:3]))
    return [
        row
        for row in rows
        if first <= cast("int", row["id"]) <= last
        and _ends(row)[0] <= instant
        and _overlaps(row, instant, OPEN_BOUND)
    ]


def _covered(
    rows: Mapping[object, tuple[Mapping[str, object], ...]], binds: Sequence[object]
) -> list[Mapping[str, object]]:
    answered: dict[int, Mapping[str, object]] = {}
    key: object = None
    since: dt.datetime | None = None
    for bind in binds:
        if not isinstance(bind, dt.datetime):
            if bind is not OPEN_BOUND:
                key = bind
        elif since is None:
            since = bind
        else:
            for row in rows.get(key, ()):
                if _overlaps(row, since, bind):
                    answered.setdefault(id(row), row)
            since = None
    return list(answered.values())


def flush_port(case: CrossObjectCase) -> OrderedAcceptingPort:
    """The port ``case``'s flush writes through: a span port over a deferred
    case's histories, otherwise one answering every read with its rows."""
    if case.deferred:
        return SpanAcceptingPort(case.stored, case.acquired)
    return OrderedAcceptingPort(case.stored)


@contextmanager
def flush_database(
    case: CrossObjectCase, port: OrderedAcceptingPort | None = None
) -> Generator[ScopedDatabase]:
    """A login-scoped handle over ``case``'s stored rows, composed outside every
    window, flushing at :data:`INSTANT`."""
    with Database(
        (flush_port(case) if port is None else port).open(),
        MODEL,
        clock=FixedClock(INSTANT),
    ) as root:
        yield root.using_database_login()


def _query(case: CrossObjectCase) -> Any:
    entity = cast("Any", case.entity)
    ids = [cast("int", row["id"]) for row in case.stored]
    return entity.where(entity.id.between(min(ids), max(ids)))


def _read_all(tx: TxnContext, case: CrossObjectCase) -> list[tuple[Any, dt.datetime | None]]:
    """Every source the case reads, beside the instant it was read as of."""
    query = _query(case)
    instants: tuple[dt.datetime | None, ...] = case.reads or (
        (INTERIOR_FROM,) if case.bounded else (None,)
    )
    sources: list[tuple[Any, dt.datetime | None]] = []
    for instant in instants:
        read = query if instant is None else query.as_of(valid_time=instant)
        found = tx.wire.find(read).results() if case.ingress == "wire" else tx.find(read).results()
        sources.extend((source, instant) for source in found)
    return sources


def _until(case: CrossObjectCase, instant: dt.datetime | None) -> dt.datetime | None:
    if case.reads:
        return cast("dt.datetime", instant) + case.reach
    return INTERIOR_UNTIL if case.bounded else None


def _amend(tx: TxnContext, case: CrossObjectCase, source: Any, until: dt.datetime | None) -> None:
    if case.ingress == "wire":
        changes = case.changes[cast("int", source["id"])]
        if until is None:
            tx.wire.amend(source, changes)
        else:
            tx.wire.amend(source, changes, until=until)
        return
    edited = source.edit(**case.changes[source.id])
    if until is None:
        tx.amend(edited)
    else:
        tx.amend(edited, until=until)


def flush_objects(handle: ScopedDatabase, case: CrossObjectCase) -> None:
    """Run ``case`` as one committed transaction: read every object, then amend
    each source through its public verb, leaving all of them to one flush —
    the pre-commit flush, or for a requesting case the read-dependency flush
    a read of no object then causes, every source still held."""

    def body(tx: TxnContext) -> None:
        sources = _read_all(tx, case)
        for source, instant in sources:
            _amend(tx, case, source, _until(case, instant))
        if case.requesting:
            nothing = cast("Any", case.entity).where(cast("Any", case.entity).id.between(0, 0))
            tx.find(nothing.as_of(valid_time=case.reads[0])).results()

    handle.transact(body)


def unmarked() -> None:
    pass


@dataclass(slots=True)
class FlushRegions:
    """The marks :func:`marked_flushes` calls: ``planning`` as finalization
    begins and ``planned`` once it has answered the plan, which is still held
    and has executed nothing; ``binding`` as each advance of a deferred span's
    scoped range binding begins and ``bound`` once it has answered the next
    ready Write Group, or ended; and ``executing`` before each Write Group's
    steps are handed to execution and ``executed`` once they return, before
    any settled write of that group completes."""

    planning: Checkpoint = unmarked
    planned: Checkpoint = unmarked
    binding: Checkpoint = unmarked
    bound: Checkpoint = unmarked
    executing: Checkpoint = unmarked
    executed: Checkpoint = unmarked


@contextmanager
def _replaced(owner: type, name: str, replacement: object) -> Generator[None]:
    original = owner.__dict__[name]
    setattr(owner, name, replacement)
    try:
        yield
    finally:
        setattr(owner, name, original)


@contextmanager
def marked_flushes(regions: FlushRegions) -> Generator[None]:
    """Every flush inside the block calling ``regions`` around production's
    own planning, range binding, and step execution:
    :meth:`WritePlanner.finalize`, ``RangeBindings.__next__``, and
    :meth:`WriteStepExecutor.execute` are wrapped for the block's whole life,
    so the wrappers are installed once rather than around each flush, and the
    marks are read from ``regions`` at each call."""
    finalize = WritePlanner.finalize
    advance = RangeBindings.__next__
    execute = WriteStepExecutor.execute

    def finalized(planner: WritePlanner, request: WritePlanningRequest, /) -> WritePlan:
        regions.planning()
        plan = finalize(planner, request)
        regions.planned()
        return plan

    def advanced(bindings: RangeBindings, /) -> WriteGroup:
        regions.binding()
        try:
            return advance(bindings)
        finally:
            regions.bound()

    def executed(
        executor: WriteStepExecutor,
        steps: tuple[PlannedStep, ...],
        /,
        *,
        allocates: bool,
        flush: FlushActivity,
        capture_insert: Callable[[WriteRow, object | None], None] | None = None,
        capture_revision: Callable[[PlannedTemporalRevision, PatchedDocument | None], None]
        | None = None,
    ) -> tuple[object, ...]:
        regions.executing()
        answered = execute(
            executor,
            steps,
            allocates=allocates,
            flush=flush,
            capture_insert=capture_insert,
            capture_revision=capture_revision,
        )
        regions.executed()
        return answered

    with (
        _replaced(WritePlanner, "finalize", finalized),
        _replaced(RangeBindings, "__next__", advanced),
        _replaced(WriteStepExecutor, "execute", executed),
    ):
        yield


def write_lowering_digest() -> str:
    from tests.unit._workload_digest_support import WRITE_SOURCES, canonical_source

    digest = hashlib.sha256()
    for index, relative in enumerate(WRITE_SOURCES):
        source = (Path(__file__).parents[2] / relative).read_text(encoding="utf-8")
        digest.update(canonical_source(source, omit_digest=index == 0))
        digest.update(b"\0")
    digest.update(structural_digest().encode("utf-8"))
    digest.update(leaf_type_digest().encode("utf-8"))
    return digest.hexdigest()
