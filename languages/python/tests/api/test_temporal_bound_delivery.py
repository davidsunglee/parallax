"""Temporal bounds read back through the shipped verbs, open and closed alike.

An open upper bound is stored as native ``infinity``, which no ``datetime``
holds; it must reach every read as the neutral unbounded instant, and a closed
bound as the instant that closed it. Each target is written once, keyed or by
predicate, so its history carries both kinds of bound, and each milestone is
read back eagerly and streamed, Typed and Wire. The Transaction-Time instants
are scripted, so every expected bound is known in advance.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, Literal, NamedTuple

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import LATEST, Attr, Bitemporal, DomainModel, Float32, TxTemporal, attr
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.entity._model import model_of
from parallax.snapshot import connect
from parallax.snapshot.handle import ScopedDatabase, Transaction
from tests._support.binary32 import narrowed, shortest_spelling
from tests._support.root_ownership import own_root

_NAMESPACE = "temporal.bound"


class Ledger(TxTemporal, table="tb_ledger", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[float] = attr(type=Float32)


class Position(Bitemporal, table="tb_position", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    amount: Attr[float] = attr(type=Float32)


_MODEL = DomainModel(Ledger, Position)

type Representation = Literal["typed", "wire"]
type Writer = Literal["keyed", "predicate"]
type Bound = dt.datetime | TemporalBound
type Pin = dt.datetime | Literal["latest"]

_INSERTED = dt.datetime(2024, 3, 1, 9, 30, 15, 123456, tzinfo=dt.UTC)
_UPDATED = dt.datetime(2024, 6, 2, 17, 45, 1, 654321, tzinfo=dt.UTC)
_VALID_FROM = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)
_CORRECTED_FROM = dt.datetime(2024, 7, 1, tzinfo=dt.UTC)
_BEFORE_CORRECTION = dt.datetime(2024, 4, 1, tzinfo=dt.UTC)
_OLD = 1.2
_NEW = 7.038530691851209e-26


class _Milestone(NamedTuple):
    """What one read of the target should state: its amount and its bounds."""

    amount: float
    tx: tuple[Bound, Bound]
    valid: tuple[Bound, Bound] | None = None

    def typed(self) -> tuple[object, ...]:
        valid = () if self.valid is None else self.valid
        return (narrowed(self.amount), *self.tx, *valid)

    def wire(self) -> tuple[object, ...]:
        valid = () if self.valid is None else tuple(map(_wire_instant, self.valid))
        amount = float(shortest_spelling(narrowed(self.amount)))
        return (amount, *map(_wire_instant, self.tx), *valid)


def _wire_instant(bound: Bound) -> str:
    return "infinity" if bound is INFINITY else f"{bound:%Y-%m-%dT%H:%M:%S.%fZ}"


# (valid pin, transaction pin) → the one milestone that read selects.
_LEDGER_READS: dict[tuple[Pin | None, Pin], _Milestone] = {
    (None, "latest"): _Milestone(_NEW, (_UPDATED, INFINITY)),
    (None, _INSERTED): _Milestone(_OLD, (_INSERTED, _UPDATED)),
}
_POSITION_READS: dict[tuple[Pin | None, Pin], _Milestone] = {
    ("latest", "latest"): _Milestone(_NEW, (_UPDATED, INFINITY), (_CORRECTED_FROM, INFINITY)),
    (_BEFORE_CORRECTION, "latest"): _Milestone(
        _OLD, (_UPDATED, INFINITY), (_VALID_FROM, _CORRECTED_FROM)
    ),
    ("latest", _INSERTED): _Milestone(_OLD, (_INSERTED, _UPDATED), (_VALID_FROM, INFINITY)),
}


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    clock = ScriptedClock([_INSERTED, _UPDATED])
    return own_root(connect(profile_run.port, _MODEL, clock=clock)).using_database_login()


def _valid_from(entity: type[Any], instant: dt.datetime) -> dt.datetime | None:
    return instant if entity is Position else None


def _typed_query(entity: type[Any], valid: Pin | None, tx: Pin) -> Any:
    def pin(at: Pin) -> object:
        return LATEST if isinstance(at, str) else at

    query = entity.where(entity.id == 1)
    if valid is None:
        return query.as_of(tx_time=pin(tx))
    return query.as_of(valid_time=pin(valid), tx_time=pin(tx))


def _wire_query(entity: type[Any], valid: Pin | None, tx: Pin) -> dict[str, object]:
    def pin(at: Pin) -> dict[str, str]:
        return {"asOf": at if isinstance(at, str) else _wire_instant(at)}

    temporal = {"transaction-time": pin(tx)}
    if valid is not None:
        temporal["valid-time"] = pin(valid)
    name = f"{_NAMESPACE}.{entity.__name__}"
    return {
        "target": name,
        "predicate": {"eq": {"attr": f"{name}.id", "value": 1}},
        "temporal": temporal,
    }


def _write(
    representation: Representation, writer: Writer, entity: type[Any]
) -> Callable[[Transaction], None]:
    name = f"{_NAMESPACE}.{entity.__name__}"
    valid_from = _valid_from(entity, _CORRECTED_FROM)

    def write(tx: Transaction) -> None:
        latest: Pin | None = "latest" if entity is Position else None
        if writer == "keyed" and representation == "typed":
            found = tx.find(_typed_query(entity, latest, "latest")).result()
            tx.update(found.edit(amount=_NEW), valid_from=valid_from)
        elif writer == "keyed":
            node = tx.wire.find(_wire_query(entity, latest, "latest")).result()
            tx.wire.update(node, {"amount": _NEW}, valid_from=valid_from)
        elif representation == "typed":
            tx.update_where(
                entity.where(entity.id == 1), entity.amount.set(_NEW), valid_from=valid_from
            )
        else:
            tx.wire.update_where(
                {"entity": name, "predicate": {"eq": {"attr": f"{name}.id", "value": 1}}},
                {"amount": _NEW},
                valid_from=valid_from,
            )

    return write


def _typed_bounds(row: Any, entity: type[Any]) -> tuple[object, ...]:
    valid = (row.valid_start, row.valid_end) if entity is Position else ()
    return (row.amount, row.tx_start, row.tx_end, *valid)


def _wire_bounds(node: Any, entity: type[Any]) -> tuple[object, ...]:
    valid = (node["validStart"], node["validEnd"]) if entity is Position else ()
    return (node["amount"], node["txStart"], node["txEnd"], *valid)


def _reads(
    db: ScopedDatabase, entity: type[Any], valid: Pin | None, tx: Pin
) -> dict[str, list[Any]]:
    typed = _typed_query(entity, valid, tx)
    wire = _wire_query(entity, valid, tx)
    typed_rows = [
        list(db.find(typed).results()),
        _streamed(db.stream(typed, batch_size=1)),
    ]
    wire_rows = [
        list(db.wire.find(wire).results()),
        _streamed(db.wire.stream(wire, batch_size=1)),
    ]
    return {
        "typed": [_typed_bounds(row, entity) for rows in typed_rows for row in rows],
        "wire": [_wire_bounds(node, entity) for rows in wire_rows for node in rows],
    }


def _streamed(stream: Any) -> list[Any]:
    with stream as rows:
        return list(rows)


@pytest.mark.parametrize("entity", [Ledger, Position], ids=["transaction-time", "bitemporal"])
@pytest.mark.parametrize("writer", ["keyed", "predicate"])
@pytest.mark.parametrize("representation", ["typed", "wire"])
def test_each_milestone_reads_back_its_open_and_closed_bounds(
    profile_run: Any, representation: Representation, writer: Writer, entity: type[Any]
) -> None:
    db = _served(profile_run)
    db.transact(
        lambda tx: tx.insert(entity(id=1, amount=_OLD), valid_from=_valid_from(entity, _VALID_FROM))
    )
    db.transact(_write(representation, writer, entity))

    milestones = _LEDGER_READS if entity is Ledger else _POSITION_READS
    for (valid, tx), milestone in milestones.items():
        observed = _reads(db, entity, valid, tx)
        assert observed == {
            "typed": [milestone.typed()] * 2,
            "wire": [milestone.wire()] * 2,
        }, (valid, tx)
