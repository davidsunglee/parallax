"""The four production write-lowering cases measured without database I/O.

One class-backed model carries transaction-time Entities under both storage
layouts. Each Entity has a One Value Object nesting another One and a Many Value
Object, so the cases exercise row serialization, instruction preparation,
settlement, and SQL lowering over the same logical member shape.

The model, values, and predecessor evidence are built at import time. A reading
supplies fresh model-scoped collaborators and opens its window only around
``lower``.
"""

import datetime as dt
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from parallax.core import Attr, Document, DomainModel, TxTemporal, ValueObject, attr
from parallax.core.base import INFINITY as OPEN_BOUND
from parallax.core.dialect import POSTGRES
from parallax.core.entity import Entity, EntityRowCodec
from parallax.core.entity._layout import CatalogedModel
from parallax.core.entity._model import model_of
from parallax.core.unit_work import (
    KeyedMutation,
    KeyedWrite,
    PlanningRequest,
    PredecessorRow,
    TemporalObservation,
    WriteObservation,
    WritePlanner,
    buffered_write,
)
from parallax.core.unit_work.instructions import prepare_typed_write
from parallax.snapshot.handle import stream_lowered
from tests._support.clock_probes import inert_instant
from tests._support.planner_probes import TEST_SUBJECT_IDENTITY

__all__ = [
    "CASES",
    "CATALOG",
    "MODEL",
    "Case",
    "case_named",
    "lower",
    "write_lowering_digest",
]

_NAMESPACE: Final = "write.lowering"


class Geo(ValueObject):
    country: Attr[str]


class Address(ValueObject):
    city: Attr[str]
    geo: Attr[Geo]


class Tag(ValueObject):
    label: Attr[str]


class ColumnsEntry(TxTemporal, table="write_lowering_columns", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


class DocumentEntry(
    TxTemporal,
    table="write_lowering_document",
    namespace=_NAMESPACE,
    layout=Document(column="payload"),
):
    id: Attr[int] = attr(primary_key=True)
    title: Attr[str]
    address: Attr[Address]
    tags: Attr[tuple[Tag, ...]]


MODEL: Final = DomainModel(ColumnsEntry, DocumentEntry)
CATALOG: Final = CatalogedModel(model_of(MODEL))


@dataclass(frozen=True, slots=True)
class Case:
    name: str
    entity: str
    mutation: KeyedMutation
    values: tuple[Entity, ...]
    observation: WriteObservation | None


def _value(cls: type[Entity], key: int, label: str) -> Entity:
    return cls(
        id=key,
        title=f"title-{label}",
        address=Address(city=f"city-{label}", geo=Geo(country=f"country-{label}")),
        tags=(Tag(label=f"tag-{label}-a"), Tag(label=f"tag-{label}-b")),
    )


_COLUMNS_OPENING: Final = _value(ColumnsEntry, 101, "opening")
_DOCUMENT_OPENING: Final = _value(DocumentEntry, 201, "opening")
_COLUMNS_PREDECESSOR: Final = _value(ColumnsEntry, 301, "before")
_DOCUMENT_PREDECESSOR: Final = _value(DocumentEntry, 401, "before")
_COLUMNS_SUCCESSOR: Final = _value(ColumnsEntry, 301, "after")
_DOCUMENT_SUCCESSOR: Final = _value(DocumentEntry, 401, "after")


def _observation(value: Entity, *, retained_document: bool) -> TemporalObservation:
    row = EntityRowCodec(CATALOG).full_row(value)
    members = {
        **row,
        "txStart": dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
        "txEnd": OPEN_BOUND,
    }
    document = (
        {name: row[name] for name in ("title", "address", "tags")} if retained_document else None
    )
    return TemporalObservation(predecessor=PredecessorRow(members, document=document))


CASES: Final[tuple[Case, ...]] = (
    Case("opening.columns", ColumnsEntry.identity.name, "insert", (_COLUMNS_OPENING,), None),
    Case("opening.document", DocumentEntry.identity.name, "insert", (_DOCUMENT_OPENING,), None),
    Case(
        "successor.columns",
        ColumnsEntry.identity.name,
        "update",
        (_COLUMNS_SUCCESSOR,),
        _observation(_COLUMNS_PREDECESSOR, retained_document=False),
    ),
    Case(
        "successor.document",
        DocumentEntry.identity.name,
        "update",
        (_DOCUMENT_SUCCESSOR,),
        _observation(_DOCUMENT_PREDECESSOR, retained_document=True),
    ),
)


def case_named(name: str) -> Case:
    for case in CASES:
        if case.name == name:
            return case
    raise KeyError(f"{name!r} is not a write-lowering case: {[case.name for case in CASES]}")


def lower(case: Case, codec: EntityRowCodec, planner: WritePlanner) -> int:
    """Serialize, prepare, settle, and drain one case through production seams."""
    rows = tuple(codec.full_row(value) for value in case.values)
    instruction = KeyedWrite(case.mutation, case.entity, rows)
    prepared = prepare_typed_write(instruction, CATALOG.meta)
    item = buffered_write(prepared, case.observation)
    plan = planner.finalize(
        PlanningRequest(
            subject_identity=TEST_SUBJECT_IDENTITY,
            transaction_instant=inert_instant(),
            concurrency="locking",
            buffered_writes=(item,),
        )
    ).plan
    for _step, _statement in stream_lowered(plan, CATALOG.meta, POSTGRES):
        pass
    return len(rows)


def write_lowering_digest() -> str:
    """The SHA-256 digest of the workload source this module defines."""
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
