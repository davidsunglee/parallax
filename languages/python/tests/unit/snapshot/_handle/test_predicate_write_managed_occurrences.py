"""Acquiring predicate writes weigh admitted occurrence assignments as the managed
values they already are, against a live database.

Ingress widens a Float32 leaf inside a value object to its exact host carrier;
the effective-change comparison then receives that carrier and must neither
decode it again nor refuse it. The same writes through a keyed verb and through
a readless predicate target are controls for the paths that never compare.
"""

from __future__ import annotations

import datetime as dt
import struct
from collections.abc import Callable
from typing import Any, Literal

import pytest

from parallax.core import (
    LATEST,
    Attr,
    Bitemporal,
    DomainModel,
    Entity,
    Float32,
    Int32,
    TxTemporal,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root
from tests._support.write_bounds import stated_start

_NAMESPACE = "managed.predicate"
_OPENED = dt.datetime(2024, 1, 1, tzinfo=dt.UTC)


class Point(ValueObject):
    f32: Attr[float] = attr(type=Float32)
    spare: Attr[float | None] = attr(type=Float32)


class VersionedGauge(Entity, table="mp_versioned_gauge", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    version: Attr[int] = attr(type=Int32, optimistic_locking=True)
    point: Attr[Point | None]
    trail: Attr[tuple[Point, ...]]


class HistoryGauge(TxTemporal, table="mp_history_gauge", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    point: Attr[Point | None]
    trail: Attr[tuple[Point, ...]]


class RectangleGauge(Bitemporal, table="mp_rectangle_gauge", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    point: Attr[Point | None]
    trail: Attr[tuple[Point, ...]]


class PlainGauge(Entity, table="mp_plain_gauge", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    point: Attr[Point | None]
    trail: Attr[tuple[Point, ...]]


_MODEL = DomainModel(VersionedGauge, HistoryGauge, RectangleGauge, PlainGauge)

type Representation = Literal["typed", "wire"]
_REPRESENTATIONS: tuple[Representation, ...] = ("typed", "wire")
_ACQUIRING: dict[str, type[Any]] = {
    "versioned": VersionedGauge,
    "transaction-time": HistoryGauge,
    "bitemporal": RectangleGauge,
}


def _float32(value: float) -> float:
    """``value`` rounded to the nearest Float32 and widened exactly."""
    return struct.unpack("<f", struct.pack("<f", value))[0]


# (authored, widened) pairs: a fractional value, the smallest subnormal, and one
# every width holds exactly.
_FRACTIONAL = (1.2, _float32(1.2))
_SUBNORMAL = (1e-45, _float32(1e-45))
_EXACT = (1.5, 1.5)
assert _FRACTIONAL[1] != _FRACTIONAL[0] and _SUBNORMAL[1] != _SUBNORMAL[0]


type Document = dict[str, float | None]


def _document(f32: float, spare: float | None = None) -> Document:
    return {"f32": f32, "spare": spare}


def _typed_point(document: Document | None) -> Point | None:
    return None if document is None else Point(**document)


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _seed(db: ScopedDatabase, entity: type[Any]) -> None:
    point = Point(**_document(_EXACT[0]))
    valid_from = _OPENED if entity is RectangleGauge else None
    db.transact(
        lambda tx: tx.insert(entity(id=1, point=point, trail=(point,)), **stated_start(valid_from))
    )


def _update_where(
    representation: Representation,
    entity: type[Any],
    point: Document | None,
    trail: tuple[Document, ...],
    *,
    month: int = 7,
) -> Callable[[Transaction], None]:
    valid_from = dt.datetime(2024, month, 1, tzinfo=dt.UTC) if entity is RectangleGauge else None

    def update(tx: Transaction) -> None:
        if representation == "typed":
            tx.amend_where(
                entity.where(entity.id == 1),
                entity.point.set(_typed_point(point)),
                entity.trail.set(tuple(Point(**element) for element in trail)),
                **stated_start(valid_from),
            )
        else:
            tx.wire.amend_where(
                {
                    "entity": f"{_NAMESPACE}.{entity.__name__}",
                    "predicate": {"eq": {"path": f"{_NAMESPACE}.{entity.__name__}.id", "value": 1}},
                },
                {"point": point, "trail": list(trail)},
                **stated_start(valid_from),
            )

    return update


def _committed(db: ScopedDatabase, entity: type[Any]) -> Any:
    query = entity.where(entity.id == 1)
    if entity is RectangleGauge:
        query = query.as_of(valid_time=LATEST)
    return db.find(query).result()


def _observed(root: Any) -> tuple[Document | None, tuple[Document, ...]]:
    def document(point: Point) -> Document:
        return {"f32": point.f32, "spare": point.spare}

    point: Point | None = root.point
    return (
        None if point is None else document(point),
        tuple(document(element) for element in root.trail),
    )


def _revision(root: Any) -> object:
    """What a written revision changes: the version, or the milestone's start."""
    return root.version if isinstance(root, VersionedGauge) else root.tx_start


@pytest.mark.parametrize("target", sorted(_ACQUIRING))
@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_an_acquiring_predicate_write_weighs_widened_float32_occurrences_as_managed(
    profile_run: Any, representation: Representation, target: str
) -> None:
    entity = _ACQUIRING[target]
    db = _served(profile_run)
    _seed(db, entity)
    seeded = _revision(_committed(db, entity))

    point = _document(_FRACTIONAL[0], _SUBNORMAL[0])
    trail = (_document(_SUBNORMAL[0]), _document(_FRACTIONAL[0], None))
    db.transact(_update_where(representation, entity, point, trail, month=7))

    changed = _committed(db, entity)
    assert _observed(changed) == (
        _document(_FRACTIONAL[1], _SUBNORMAL[1]),
        (_document(_SUBNORMAL[1]), _document(_FRACTIONAL[1], None)),
    )
    assert _revision(changed) != seeded

    # The same authored values restore what the row now holds: no revision.
    db.transact(_update_where(representation, entity, point, trail, month=8))
    assert _revision(_committed(db, entity)) == _revision(changed)

    # A null `one` and an empty `many` are a change, and then themselves a no-op.
    db.transact(_update_where(representation, entity, None, (), month=9))
    cleared = _committed(db, entity)
    assert _observed(cleared) == (None, ())
    assert _revision(cleared) != _revision(changed)
    db.transact(_update_where(representation, entity, None, (), month=10))
    assert _revision(_committed(db, entity)) == _revision(cleared)


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_readless_predicate_write_stores_widened_float32_occurrences(
    profile_run: Any, representation: Representation
) -> None:
    db = _served(profile_run)
    _seed(db, PlainGauge)

    point = _document(_FRACTIONAL[0], _SUBNORMAL[0])
    db.transact(_update_where(representation, PlainGauge, point, (point,)))

    widened = _document(_FRACTIONAL[1], _SUBNORMAL[1])
    assert _observed(_committed(db, PlainGauge)) == (widened, (widened,))


@pytest.mark.parametrize("representation", _REPRESENTATIONS)
def test_a_keyed_write_stores_widened_float32_occurrences(
    profile_run: Any, representation: Representation
) -> None:
    db = _served(profile_run)
    _seed(db, VersionedGauge)
    point = _document(_FRACTIONAL[0], _SUBNORMAL[0])

    def update(tx: Transaction) -> None:
        if representation == "typed":
            found = tx.find(VersionedGauge.where(VersionedGauge.id == 1)).result()
            tx.amend(found.edit(point=_typed_point(point), trail=(_typed_point(point),)))
        else:
            node = tx.wire.find(
                {
                    "target": f"{_NAMESPACE}.VersionedGauge",
                    "predicate": {"eq": {"path": f"{_NAMESPACE}.VersionedGauge.id", "value": 1}},
                }
            ).result()
            tx.wire.amend(node, {"point": point, "trail": [point]})

    db.transact(update)

    committed = _committed(db, VersionedGauge)
    widened = _document(_FRACTIONAL[1], _SUBNORMAL[1])
    assert _observed(committed) == (widened, (widened,))
    assert committed.version == 2
