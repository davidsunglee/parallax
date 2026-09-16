"""The keyed-write workloads measured without database I/O, from Typed or Wire
input through preparation, settlement, SQL lowering, and the driver's own
document serialization.

One class-backed model carries the categorical matrix — Transaction-Time-Only,
non-temporal, and Bitemporal Entities under both storage layouts, each with a
One Value Object nesting another One and a Many — beside the geometry Entities
:mod:`tests.unit._structural_geometry_support` declares. The geometry levels
open a lineage; the changed-ancestor levels succeed one, changing a single leaf
of a wide root occurrence so the cost of replacing that occurrence is read
against its declared width. Every case names its ingress, layout, mutation,
authored values, and predecessor evidence; the window a reading opens is
:func:`lower` alone.

The window ends where the driver would hand bytes to the socket: each lowered
statement's binds cross the production PostgreSQL bind adaptation and are then
dumped by psycopg's own transformer, which is the serialization
``cursor.execute`` performs. Database execution and network time are outside it.

Exported names carry no leading underscore: importing an underscored name across
modules is a ``reportPrivateUsage`` error under pyright strict, so privacy is
carried by this MODULE's underscore. Never imported by production code.
"""

import datetime as dt
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from psycopg import postgres
from psycopg.abc import Buffer
from psycopg.adapt import PyFormat, Transformer

from parallax.conformance.workloads import GEOMETRY_LEVELS, structural_digest
from parallax.core import (
    Attr,
    Bitemporal,
    Document,
    DomainModel,
    Entity,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.dialect import POSTGRES
from parallax.core.entity import EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.sql_gen import LoweredStatement
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    PlanningRequest,
    PredecessorRow,
    TemporalObservation,
    WriteObservation,
    WritePlan,
    WritePlanner,
    buffered_write,
)
from parallax.core.unit_work.instructions import (
    PreparedKeyedWrite,
    prepare_typed_write,
    prepare_wire_write,
)
from parallax.postgres._connection import adapt_binds
from parallax.snapshot.handle import stream_lowered
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_SUBJECT_IDENTITY
from tests.unit import _predicate_acquisition_support as acquisition_support
from tests.unit import _structural_geometry_support as geometry_support

__all__ = [
    "ANCESTOR_KEY",
    "CASES",
    "CATALOG",
    "ENTITY_CLASSES",
    "MODEL",
    "Case",
    "Ingress",
    "Layout",
    "Settled",
    "case_named",
    "lower",
    "lowered",
    "serialize",
    "settle",
    "write_lowering_digest",
]

type Layout = Literal["columns", "document"]
type Ingress = Literal["typed", "wire"]

_NAMESPACE: Final = "write.lowering"

TX_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
VALID_START: Final = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
INTERIOR_FROM: Final = dt.datetime(2026, 3, 1, tzinfo=dt.UTC)
INTERIOR_UNTIL: Final = dt.datetime(2026, 9, 1, tzinfo=dt.UTC)
"""A Valid-Time window strictly inside the predecessor's open interval, so a
Bitemporal ``updateUntil`` produces a close, a carried head, a changed middle,
and a carried tail."""

WIRE_INTERIOR_FROM: Final = "2026-03-01T00:00:00.000000Z"
WIRE_INTERIOR_UNTIL: Final = "2026-09-01T00:00:00.000000Z"


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
_CATEGORICAL_DOCUMENT_MEMBERS: Final[tuple[str, ...]] = ("title", "address", "tags")


@dataclass(frozen=True, slots=True)
class Case:
    """One keyed write and the evidence it is prepared against.

    ``values`` are the Typed instances a Typed case serializes inside the
    window; ``wire_rows`` are the authored mappings a Wire case hands to
    preparation, composed outside it exactly as a caller's payload arrives.
    ``statements`` is how many statements the case lowers to.
    """

    name: str
    family: str
    entity: type[Entity]
    ingress: Ingress
    layout: Layout
    mutation: KeyedMutation
    values: tuple[Entity, ...]
    wire_rows: tuple[Mapping[str, object], ...]
    observation: WriteObservation | None
    statements: int
    valid_from: dt.datetime | str | None = None
    until: dt.datetime | str | None = None


@dataclass(frozen=True, slots=True)
class Settled:
    """What production retains once a keyed write is prepared and settled and
    before it is lowered: the serialized rows, the prepared instruction, the
    buffered item, and the plan."""

    rows: tuple[Mapping[str, object], ...]
    prepared: PreparedKeyedWrite
    item: object
    plan: WritePlan


_CODEC: Final = EntityRowCodec(CATALOG)


def _value(cls: type[Entity], key: int, label: str) -> Entity:
    return cls(
        id=key,
        title=f"title-{label}",
        address=Address(city=f"city-{label}", geo=Geo(country=f"country-{label}")),
        tags=(Tag(label=f"tag-{label}-a"), Tag(label=f"tag-{label}-b")),
    )


def _observation(
    value: Entity,
    *,
    layout: Layout,
    document_members: Sequence[str] = _CATEGORICAL_DOCUMENT_MEMBERS,
) -> TemporalObservation:
    row = _CODEC.full_row(value)
    members: dict[str, object] = {**row, "txStart": TX_START, "txEnd": OPEN_BOUND}
    if isinstance(value, Bitemporal):
        members.update(validStart=VALID_START, validEnd=OPEN_BOUND)
    document = {name: row[name] for name in document_members} if layout == "document" else None
    return TemporalObservation(predecessor=PredecessorRow(members, document=document))


def _wire_rows(values: Sequence[Entity]) -> tuple[Mapping[str, object], ...]:
    return tuple(_CODEC.full_row(value) for value in values)


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
    value = _value(cls, key, label)
    observation = (
        None if predecessor is None else _observation(_value(cls, key, predecessor), layout=layout)
    )
    valid_from: dt.datetime | str | None = None
    until: dt.datetime | str | None = None
    if bounded:
        valid_from = INTERIOR_FROM if ingress == "typed" else WIRE_INTERIOR_FROM
        until = INTERIOR_UNTIL if ingress == "typed" else WIRE_INTERIOR_UNTIL
    return Case(
        f"{family}.{operation}.{layout}.{ingress}",
        family,
        cls,
        ingress,
        layout,
        mutation,
        (value,) if ingress == "typed" else (),
        _wire_rows((value,)) if ingress == "wire" else (),
        observation,
        statements,
        valid_from,
        until,
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
                    statements=2,
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
                    predecessor=None,
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
        Case(
            f"geometry.{level.id}.{layout}.typed",
            f"geometry-{level.family}",
            geometry_support.entity_class(level, layout),
            "typed",
            layout,
            "insert",
            (geometry_support.instance(level, layout, 1),),
            (),
            None,
            1,
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
        Case(
            f"ancestor.{level.id}.{layout}.typed",
            f"ancestor-{level.family}",
            geometry_support.successor_class(level, layout),
            "typed",
            layout,
            "update",
            (geometry_support.successor_instance(level, layout, ANCESTOR_KEY, changed=True),),
            (),
            _observation(
                geometry_support.successor_instance(level, layout, ANCESTOR_KEY, changed=False),
                layout=layout,
                document_members=geometry_support.DOCUMENT_MEMBERS,
            ),
            2,
        )
        for level in geometry_support.ANCESTOR_LEVELS
        for layout in geometry_support.LAYOUTS
    )


CASES: Final[tuple[Case, ...]] = (
    *_categorical_cases(),
    *_geometry_cases(),
    *_ancestor_cases(),
)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"{name!r} is not a write-lowering case: {[case.name for case in CASES]}")


def _instruction(case: Case, rows: tuple[Mapping[str, object], ...]) -> KeyedWrite:
    return KeyedWrite(
        case.mutation,
        case.entity.identity.name,
        rows,
        valid_from=case.valid_from,
        until=case.until,
    )


def settle(case: Case, codec: EntityRowCodec, planner: WritePlanner) -> Settled:
    """Serialize, prepare, and settle one case, retaining what production does."""
    rows = (
        tuple(codec.full_row(value) for value in case.values)
        if case.ingress == "typed"
        else case.wire_rows
    )
    instruction = _instruction(case, rows)
    prepared = (
        prepare_typed_write(instruction, CATALOG.meta)
        if case.ingress == "typed"
        else prepare_wire_write(instruction, CATALOG.meta)
    )
    assert isinstance(prepared, PreparedKeyedWrite)
    item = buffered_write(prepared, case.observation)
    plan = planner.finalize(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="locking",
            buffered_writes=(item,),
        )
    ).plan
    return Settled(rows, prepared, item, plan)


def serialize(statement: LoweredStatement) -> Sequence[Buffer | None]:
    """The driver bytes ``statement``'s binds become: production bind adaptation
    followed by the transformer dump ``cursor.execute`` performs."""
    binds = adapt_binds(statement.binds)
    transformer = Transformer(postgres.adapters)
    return transformer.dump_sequence(binds, [PyFormat.AUTO] * len(binds))


def lower(case: Case, codec: EntityRowCodec, planner: WritePlanner) -> int:
    """The complete keyed-write window: ingress through driver serialization."""
    settled = settle(case, codec, planner)
    for _step, statement in stream_lowered(settled.plan, CATALOG.meta, POSTGRES):
        serialize(statement)
    return len(settled.rows)


def lowered(
    case: Case, codec: EntityRowCodec, planner: WritePlanner
) -> tuple[tuple[LoweredStatement, Sequence[Buffer | None]], ...]:
    """Every statement one case lowers to beside its dumped binds, for a suite
    grading what the window produced."""
    settled = settle(case, codec, planner)
    return tuple(
        (statement, serialize(statement))
        for _step, statement in stream_lowered(settled.plan, CATALOG.meta, POSTGRES)
    )


def write_lowering_digest() -> str:
    """The SHA-256 digest of every source this workload is defined by."""
    digest = hashlib.sha256()
    for module in (
        Path(__file__),
        Path(geometry_support.__file__),
        Path(acquisition_support.__file__),
    ):
        digest.update(module.read_bytes())
        digest.update(b"\0")
    digest.update(structural_digest().encode("utf-8"))
    return digest.hexdigest()
