"""Timestamps read through the shipped verbs as UTC instants, whatever the session zone.

A deployment's session time zone is its own: the adapter leaves it as
configured, and a session that is not exactly ``UTC`` spells every native
``timestamptz`` in its own zone. Every expected instant and spelling is stated
here rather than derived from what is graded.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any, NamedTuple

import pytest

from parallax.conformance.scripted_clock import ScriptedClock
from parallax.core import LATEST, Attr, Bitemporal, Document, DomainModel, Entity, attr
from parallax.core.base import INFINITY, TemporalBound
from parallax.core.entity._model import model_of
from parallax.postgres import PoolOptions
from parallax.snapshot import Database, ScopedDatabase, TxnContext
from tests._support.root_ownership import own_root

_NAMESPACE = "timestamp.delivery"


class ColumnsEvent(Entity, table="td_columns_event", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    at: Attr[dt.datetime]


class DocumentEvent(Entity, table="td_document_event", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    at: Attr[dt.datetime]


class ColumnsSpan(Bitemporal, table="td_columns_span", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    at: Attr[dt.datetime]


class DocumentSpan(Bitemporal, table="td_document_span", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    at: Attr[dt.datetime]


_MODEL = DomainModel(ColumnsEvent, DocumentEvent, ColumnsSpan, DocumentSpan)


class _Instant(NamedTuple):
    typed: dt.datetime
    wire: str


class _Open(NamedTuple):
    typed: TemporalBound
    wire: str


type _Bound = _Instant | _Open

_OPEN = _Open(INFINITY, "infinity")
# America/New_York reads these on other local dates, either side of a DST
# change, and within a microsecond of one.
_WINTER = _Instant(
    dt.datetime(2031, 1, 2, 12, 4, 5, 1, tzinfo=dt.UTC), "2031-01-02T12:04:05.000001Z"
)
_LEAP_DAY = _Instant(
    dt.datetime(2024, 3, 1, 2, 30, 15, 123456, tzinfo=dt.UTC), "2024-03-01T02:30:15.123456Z"
)
_SUMMER = _Instant(
    dt.datetime(2024, 7, 4, 3, 59, 59, 999999, tzinfo=dt.UTC), "2024-07-04T03:59:59.999999Z"
)
_INSERTED = _Instant(
    dt.datetime(2024, 3, 10, 6, 59, 59, 999999, tzinfo=dt.UTC), "2024-03-10T06:59:59.999999Z"
)
_UPDATED = _Instant(
    dt.datetime(2024, 11, 3, 6, 0, 0, 1, tzinfo=dt.UTC), "2024-11-03T06:00:00.000001Z"
)
_VALID_FROM = _Instant(
    dt.datetime(2024, 1, 1, 4, 59, 59, 1, tzinfo=dt.UTC), "2024-01-01T04:59:59.000001Z"
)
_CORRECTED_FROM = _Instant(
    dt.datetime(2024, 6, 1, 0, 0, 0, 500000, tzinfo=dt.UTC), "2024-06-01T00:00:00.500000Z"
)
_BEFORE_CORRECTION = _Instant(dt.datetime(2024, 4, 1, tzinfo=dt.UTC), "2024-04-01T00:00:00.000000Z")

_STORED = {1: _WINTER, 2: _LEAP_DAY}
_CORRECTED = _SUMMER

_ZONES = pytest.mark.parametrize("zone", ["UTC", "Etc/UTC", "America/New_York"])


class _Milestone(NamedTuple):
    at: dict[int, _Instant]
    tx: tuple[_Instant, _Bound]
    valid: tuple[_Instant, _Bound]


type _Pin = _Instant | None

_SPAN_READS: dict[tuple[_Pin, _Pin], _Milestone] = {
    (None, None): _Milestone(
        dict.fromkeys(_STORED, _CORRECTED), (_UPDATED, _OPEN), (_CORRECTED_FROM, _OPEN)
    ),
    (_BEFORE_CORRECTION, None): _Milestone(
        _STORED, (_UPDATED, _OPEN), (_VALID_FROM, _CORRECTED_FROM)
    ),
    (None, _INSERTED): _Milestone(_STORED, (_INSERTED, _UPDATED), (_VALID_FROM, _OPEN)),
}


def _served(profile_run: Any, zone: str) -> tuple[ScopedDatabase, Any]:
    profile_run.reset(model_of(_MODEL), {})
    runtime = profile_run.configured(
        pool=PoolOptions(min_size=1, max_size=1), settings={"timezone": zone}
    ).open()
    try:
        root = Database(runtime, _MODEL, clock=ScriptedClock([_INSERTED.typed, _UPDATED.typed]))
    except BaseException:
        runtime.close()
        raise
    return own_root(root).using_database_login(), runtime


def _session_zone(runtime: Any) -> str:
    with runtime.login_execution().new_context() as connection:
        ((zone,),) = connection.execute("select current_setting('timezone')", [])
    return zone


def _typed(value: object) -> object:
    if value is INFINITY:
        return value
    assert isinstance(value, dt.datetime)
    return (type(value), value.tzinfo is dt.UTC, value)


def _expected_typed(bound: _Bound) -> object:
    if isinstance(bound, _Open):
        return bound.typed
    return (dt.datetime, True, bound.typed)


def _streamed(stream: Any) -> list[Any]:
    with stream as rows:
        return list(rows)


def _read(
    db: ScopedDatabase,
    typed: Any,
    wire: dict[str, object],
    typed_fields: tuple[str, ...],
    wire_fields: tuple[str, ...],
) -> dict[str, list[list[tuple[object, ...]]]]:
    typed_reads = [list(db.find(typed).results()), _streamed(db.stream(typed, batch_size=1))]
    wire_reads = [
        list(db.wire.find(wire).results()),
        _streamed(db.wire.stream(wire, batch_size=1)),
    ]
    return {
        "typed": [
            [(row.id, *(_typed(getattr(row, field)) for field in typed_fields)) for row in rows]
            for rows in typed_reads
        ],
        "wire": [
            [(node["id"], *(node[field] for field in wire_fields)) for node in nodes]
            for nodes in wire_reads
        ],
    }


def _wire_query(entity: type[Any], **clauses: object) -> dict[str, object]:
    name = f"{_NAMESPACE}.{entity.__name__}"
    return {
        "target": name,
        "predicate": {"true": {}},
        "orderBy": [{"attr": f"{name}.id", "direction": "asc"}],
        **clauses,
    }


@_ZONES
@pytest.mark.parametrize("entity", [ColumnsEvent, DocumentEvent], ids=["columns", "document"])
def test_a_timestamp_attribute_reads_back_as_its_utc_instant(
    profile_run: Any, zone: str, entity: type[Any]
) -> None:
    db, runtime = _served(profile_run, zone)
    db.transact(lambda tx: [tx.insert(entity(id=key, at=at.typed)) for key, at in _STORED.items()])

    observed = _read(
        db,
        entity.where(entity.all).order_by(entity.id.asc()),
        _wire_query(entity),
        ("at",),
        ("at",),
    )

    assert observed == {
        "typed": [[(key, _expected_typed(at)) for key, at in _STORED.items()]] * 2,
        "wire": [[(key, at.wire) for key, at in _STORED.items()]] * 2,
    }
    assert _session_zone(runtime) == zone


def _typed_span_query(entity: type[Any], valid: _Pin, tx: _Pin) -> Any:
    def pin(at: _Pin) -> object:
        return LATEST if at is None else at.typed

    return (
        entity.where(entity.all)
        .order_by(entity.id.asc())
        .as_of(valid_time=pin(valid), tx_time=pin(tx))
    )


def _wire_span_query(entity: type[Any], valid: _Pin, tx: _Pin) -> dict[str, object]:
    def pin(at: _Pin) -> dict[str, str]:
        return {"asOf": "latest" if at is None else at.wire}

    return _wire_query(entity, temporal={"valid-time": pin(valid), "transaction-time": pin(tx)})


def _corrected(entity: type[Any]) -> Callable[[TxnContext], object]:
    def correct(tx: TxnContext) -> object:
        return tx.amend_where(
            entity.where(entity.all),
            entity.at.set(_CORRECTED.typed),
            valid_from=_CORRECTED_FROM.typed,
        )

    return correct


@_ZONES
@pytest.mark.parametrize("entity", [ColumnsSpan, DocumentSpan], ids=["columns", "document"])
def test_temporal_coordinates_read_back_as_utc_instants_or_the_open_bound(
    profile_run: Any, zone: str, entity: type[Any]
) -> None:
    db, runtime = _served(profile_run, zone)
    db.transact(
        lambda tx: [
            tx.insert(entity(id=key, at=at.typed), valid_from=_VALID_FROM.typed)
            for key, at in _STORED.items()
        ]
    )
    db.transact(_corrected(entity))

    for (valid, tx), milestone in _SPAN_READS.items():
        bounds = (*milestone.tx, *milestone.valid)
        observed = _read(
            db,
            _typed_span_query(entity, valid, tx),
            _wire_span_query(entity, valid, tx),
            ("at", "tx_start", "tx_end", "valid_start", "valid_end"),
            ("at", "txStart", "txEnd", "validStart", "validEnd"),
        )
        assert observed == {
            "typed": [
                [
                    (key, *(_expected_typed(instant) for instant in (at, *bounds)))
                    for key, at in milestone.at.items()
                ]
            ]
            * 2,
            "wire": [
                [
                    (key, *(instant.wire for instant in (at, *bounds)))
                    for key, at in milestone.at.items()
                ]
            ]
            * 2,
        }, (valid, tx)
    assert _session_zone(runtime) == zone
