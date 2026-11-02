"""The model, fixtures and read shapes the standby proofs share.

One logical row shape is stored under both Storage Layouts, and each read
shape reduces what it delivered to the identities it saw, so a proof states
visibility once and runs it over every representation and layout.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, Final, cast

from parallax.conformance._replication import ReplicationPair
from parallax.core import Attr, Document, DomainModel, Entity, attr
from parallax.core.entity._model import model_of
from parallax.core.object_query import deserialize
from parallax.snapshot import ScopedDatabase, SnapshotStream, TxnContext
from tests._support.query_probes import canonical_document

_NAMESPACE = "replication.visibility"


class Ledger(Entity, table="rv_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    memo: Attr[str]


class Folio(Entity, table="rv_folio", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    memo: Attr[str]


MODEL: Final = DomainModel(Ledger, Folio)

LAYOUTS: Final[Mapping[str, type[Ledger] | type[Folio]]] = {"columns": Ledger, "document": Folio}

SEEDED: Final = [1, 2]
"""The identities every proof starts from, already applied on the standby."""


def replicated(profile_run: Any) -> ReplicationPair:
    """This run's pair, reset to the seeded rows on both servers."""
    pair: ReplicationPair = profile_run.replication()
    rows = [{"id": identity, "memo": f"seeded-{identity}"} for identity in SEEDED]
    pair.reset(
        model_of(MODEL),
        {f"{_NAMESPACE}.{entity.__name__}": rows for entity in LAYOUTS.values()},
    )
    return pair


def everything(entity: type[Ledger] | type[Folio]) -> Any:
    target: Any = entity
    return target.where(target.id >= 0).order_by(target.id.asc())


def insert(db: ScopedDatabase, entity: type[Ledger] | type[Folio], *identities: int) -> None:
    def body(tx: TxnContext) -> None:
        for identity in identities:
            tx.insert(entity(id=identity, memo=f"added-{identity}"))

    db.transact(body)


def identity(item: object) -> int:
    """The identity a Typed instance or a Wire node delivered."""
    found: Any = item
    return cast("int", found["id"] if isinstance(found, Mapping) else found.id)


def _identities(found: Sequence[object]) -> list[int]:
    return [identity(item) for item in found]


type Streamed = Callable[[Any, type[Ledger] | type[Folio]], SnapshotStream[Any]]

STREAMS: Final[Mapping[str, Streamed]] = {
    "typed": lambda reader, entity: reader.stream(everything(entity), batch_size=1),
    "wire": lambda reader, entity: reader.wire.stream(
        canonical_document(everything(entity), MODEL), batch_size=1
    ),
}
"""A one-row-per-page stream in each representation, from a scope or a transaction."""


def _drained(stream: SnapshotStream[Any]) -> list[Any]:
    with stream as opened:
        return list(opened)


type Read = Callable[[ScopedDatabase, type[Ledger] | type[Folio]], list[int]]

READS: Final[Mapping[str, Read]] = {
    "typed-eager": lambda db, entity: _identities(list(db.find(everything(entity)).results())),
    "typed-stream": lambda db, entity: _identities(_drained(STREAMS["typed"](db, entity))),
    "wire-eager": lambda db, entity: _identities(
        list(db.wire.find(canonical_document(everything(entity), MODEL)).results())
    ),
    "wire-stream": lambda db, entity: _identities(_drained(STREAMS["wire"](db, entity))),
    "rows": lambda db, entity: _identities(
        db.read_rows(deserialize(canonical_document(everything(entity), MODEL))).rows
    ),
}
"""Every standalone read shape, reduced to the identities it delivered in order."""
