"""Scalar collections round-trip through the shipped verbs under both layouts.

A collection is an ordered, duplicate-preserving tuple of one declared scalar
type. It is stored as one canonical array — a structured Column of its own under
Columns, an array member of the shared document under Document — and every
element keeps its scalar's normalization, so duplicates created by
normalization survive. Typed reads publish immutable tuples and Wire reads the
canonical Wire array. Expected stored arrays are spelled independently here.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, cast

import pytest

from parallax.conformance import engine
from parallax.core import (
    Attr,
    Document,
    DomainModel,
    Entity,
    Float32,
    Int32,
    ValueObject,
    attr,
)
from parallax.core.entity._model import model_of
from parallax.snapshot import ScopedDatabase, Transaction, connect
from tests._support.root_ownership import own_root

_NAMESPACE = "scalar.collection"


class Detail(ValueObject):
    labels: Attr[tuple[str, ...]] = attr()


class Line(ValueObject):
    sku: Attr[str] = attr()
    marks: Attr[tuple[int, ...]] = attr(type=Int32)
    detail: Attr[Detail | None] = attr()


class Order(Entity, table="sc_order", namespace=_NAMESPACE):
    id: Attr[int] = attr(primary_key=True)
    flags: Attr[tuple[bool, ...]] = attr()
    smalls: Attr[tuple[int, ...]] = attr(type=Int32)
    counts: Attr[tuple[int, ...]] = attr()
    ratios: Attr[tuple[float, ...]] = attr(type=Float32)
    scores: Attr[tuple[float, ...]] = attr()
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=12, scale=2)
    tags: Attr[tuple[str, ...]] = attr(column="tag_list")
    blobs: Attr[tuple[bytes, ...]] = attr()
    days: Attr[tuple[dt.date, ...]] = attr()
    times: Attr[tuple[dt.time, ...]] = attr()
    instants: Attr[tuple[dt.datetime, ...]] = attr()
    keys: Attr[tuple[uuid.UUID, ...]] = attr()
    detail: Attr[Detail | None] = attr()
    lines: Attr[tuple[Line, ...]] = attr()


class Sheet(Entity, table="sc_sheet", namespace=_NAMESPACE, layout=Document()):
    id: Attr[int] = attr(primary_key=True)
    flags: Attr[tuple[bool, ...]] = attr()
    smalls: Attr[tuple[int, ...]] = attr(type=Int32)
    counts: Attr[tuple[int, ...]] = attr()
    ratios: Attr[tuple[float, ...]] = attr(type=Float32)
    scores: Attr[tuple[float, ...]] = attr()
    amounts: Attr[tuple[Decimal, ...]] = attr(precision=12, scale=2)
    tags: Attr[tuple[str, ...]] = attr()
    blobs: Attr[tuple[bytes, ...]] = attr()
    days: Attr[tuple[dt.date, ...]] = attr()
    times: Attr[tuple[dt.time, ...]] = attr()
    instants: Attr[tuple[dt.datetime, ...]] = attr()
    keys: Attr[tuple[uuid.UUID, ...]] = attr()
    detail: Attr[Detail | None] = attr()
    lines: Attr[tuple[Line, ...]] = attr()


_MODEL = DomainModel(Order, Sheet)

type Layout = Literal["columns", "document"]
_LAYOUTS: tuple[Layout, ...] = ("columns", "document")
_ENTITIES: Mapping[Layout, Any] = {"columns": Order, "document": Sheet}
_TABLES: Mapping[Layout, str] = {"columns": "sc_order", "document": "sc_sheet"}

_KEY = uuid.UUID("12345678-1234-5678-1234-567812345678")
_OSLO = dt.timezone(dt.timedelta(hours=2))

_AUTHORED: Mapping[str, tuple[object, ...]] = {
    "flags": (True, False, True),
    "smalls": (3, -2, 3),
    "counts": (9_007_199_254_740_993, 0),
    "ratios": (1.2, -0.0),
    "scores": (0.1, -0.0, 2.5),
    "amounts": (Decimal("1.5"), Decimal("1.50"), 7),
    "tags": ("b", "a", "b"),
    "blobs": (b"\x0a\xff", b""),
    "days": (dt.date(2024, 2, 29),),
    "times": (dt.time(13, 5, 7, 250),),
    "instants": (dt.datetime(2024, 6, 1, 12, 0, tzinfo=_OSLO),),
    "keys": (_KEY, _KEY),
}
"""One value per scalar type, with order, duplicates, and duplicates created by
normalization: ``Decimal("1.5")`` and ``Decimal("1.50")`` both store ``1.50``,
and ``-0.0`` stores positive zero."""

_STORED: Mapping[str, list[object]] = {
    "flags": [True, False, True],
    "smalls": [3, -2, 3],
    "counts": [9_007_199_254_740_993, 0],
    "ratios": [1.2, 0.0],
    "scores": [0.1, 0, 2.5],
    "amounts": ["1.50", "1.50", "7.00"],
    "tags": ["b", "a", "b"],
    "blobs": ["0aff", ""],
    "days": ["2024-02-29"],
    "times": ["13:05:07.000250"],
    "instants": ["2024-06-01T10:00:00.000000Z"],
    "keys": [str(_KEY), str(_KEY)],
}
"""The canonical stored array of each collection above, spelled independently."""

_PUBLISHED: Mapping[str, tuple[object, ...]] = {
    "flags": (True, False, True),
    "smalls": (3, -2, 3),
    "counts": (9_007_199_254_740_993, 0),
    "ratios": (1.2000000476837158, 0.0),
    "scores": (0.1, 0.0, 2.5),
    "amounts": (Decimal("1.50"), Decimal("1.50"), Decimal("7.00")),
    "tags": ("b", "a", "b"),
    "blobs": (b"\x0a\xff", b""),
    "days": (dt.date(2024, 2, 29),),
    "times": (dt.time(13, 5, 7, 250),),
    "instants": (dt.datetime(2024, 6, 1, 10, 0, tzinfo=dt.UTC),),
    "keys": (_KEY, _KEY),
}


def _served(profile_run: Any) -> ScopedDatabase:
    profile_run.reset(model_of(_MODEL), {})
    return own_root(connect(profile_run.port, _MODEL)).using_database_login()


def _stored_row(profile_run: Any, layout: Layout) -> Mapping[str, object]:
    state = engine.read_table_state(profile_run.port, model_of(_MODEL))
    (row,) = state[_TABLES[layout]]
    return row


def _stored_members(profile_run: Any, layout: Layout) -> Mapping[str, object]:
    row = _stored_row(profile_run, layout)
    if layout == "document":
        return cast("Mapping[str, object]", row["payload"])
    return {("tags" if name == "tag_list" else name): value for name, value in row.items()}


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_every_scalar_type_round_trips_in_order_with_duplicates(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run)
    entity = _ENTITIES[layout]
    db.transact(lambda tx: tx.insert(entity(id=1, **_AUTHORED)))

    stored = _stored_members(profile_run, layout)
    assert {name: stored[name] for name in _STORED} == _STORED

    read = db.find(entity.where(entity.id == 1)).result()
    for name, expected in _PUBLISHED.items():
        assert getattr(read, name) == expected
        assert type(getattr(read, name)) is tuple


def _wire_query(layout: Layout) -> dict[str, object]:
    return {"target": f"{_NAMESPACE}.{_ENTITIES[layout].__name__}", "predicate": {"true": {}}}


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_a_wire_insert_stores_and_publishes_the_canonical_arrays(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run)
    name = f"{_NAMESPACE}.{_ENTITIES[layout].__name__}"
    authored: dict[str, object] = {"id": 1, **{key: list(value) for key, value in _STORED.items()}}
    authored["ratios"] = [1.2000000476837158, -0.0]
    db.transact(lambda tx: tx.wire.insert(name, authored))

    stored = _stored_members(profile_run, layout)
    assert {key: stored[key] for key in _STORED} == _STORED

    (node,) = db.wire.find(_wire_query(layout)).results()
    assert {key: node[key] for key in _STORED} == _STORED
    typed = db.find(_ENTITIES[layout].where(_ENTITIES[layout].id == 1)).result()
    assert {key: getattr(typed, key) for key in _PUBLISHED} == _PUBLISHED


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_omitted_collections_store_and_read_as_empty(profile_run: Any, layout: Layout) -> None:
    db = _served(profile_run)
    entity = _ENTITIES[layout]
    db.transact(lambda tx: tx.insert(entity(id=1)))

    stored = _stored_members(profile_run, layout)
    assert all(stored[key] == [] for key in _STORED)
    read = db.find(entity.where(entity.id == 1)).result()
    assert all(getattr(read, key) == () for key in _STORED)
    (node,) = db.wire.find(_wire_query(layout)).results()
    assert all(node[key] == [] for key in _STORED)


_NESTED_DETAIL = Detail(labels=("x", "y", "x"))
_NESTED_LINES = (
    Line(sku="a", marks=(2, 1, 2), detail=Detail(labels=("deep",))),
    Line(sku="b", marks=()),
)


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_collections_inside_single_and_many_value_objects_round_trip(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run)
    entity = _ENTITIES[layout]
    db.transact(lambda tx: tx.insert(entity(id=1, detail=_NESTED_DETAIL, lines=_NESTED_LINES)))

    stored = _stored_members(profile_run, layout)
    assert stored["detail"] == {"labels": ["x", "y", "x"]}
    assert stored["lines"] == [
        {"sku": "a", "marks": [2, 1, 2], "detail": {"labels": ["deep"]}},
        {"sku": "b", "marks": []},
    ]
    read = db.find(entity.where(entity.id == 1)).result()
    assert read.detail == _NESTED_DETAIL
    assert read.lines == _NESTED_LINES
    (node,) = db.wire.find(_wire_query(layout)).results()
    assert node["detail"] == {"labels": ["x", "y", "x"]}
    assert node["lines"] == stored["lines"]


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_edits_and_assignments_replace_and_clear_whole_collections(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run)
    entity = _ENTITIES[layout]
    db.transact(lambda tx: tx.insert(entity(id=1, tags=("a",), counts=(1, 2))))

    def edit(tx: Transaction) -> None:
        read = tx.find(entity.where(entity.id == 1)).result()
        tx.amend(read.edit(tags=("c", "b", "c"), counts=()))

    db.transact(edit)
    stored = _stored_members(profile_run, layout)
    assert (stored["tags"], stored["counts"]) == (["c", "b", "c"], [])

    db.transact(
        lambda tx: tx.amend_where(
            entity.where(entity.id == 1),
            entity.tags.set(()),
            entity.counts.set((5, 5)),
        )
    )
    stored = _stored_members(profile_run, layout)
    assert (stored["tags"], stored["counts"]) == ([], [5, 5])

    db.transact(
        lambda tx: tx.wire.amend_where(
            {
                "entity": f"{_NAMESPACE}.{entity.__name__}",
                "predicate": {"eq": {"path": f"{_NAMESPACE}.{entity.__name__}.id", "value": 1}},
            },
            {"tags": ["z"]},
        )
    )
    read = db.find(entity.where(entity.id == 1)).result()
    assert (read.tags, read.counts) == (("z",), (5, 5))


def test_a_document_update_keeps_unknown_content_beside_an_assigned_collection(
    profile_run: Any,
) -> None:
    db = _served(profile_run)
    db.transact(lambda tx: tx.insert(Sheet(id=1, tags=("a",), counts=(1,))))
    profile_run.port.execute_write(
        """update sc_sheet set payload = payload || '{"futureKey": [1, "x"]}'::jsonb""", []
    )

    db.transact(lambda tx: tx.amend_where(Sheet.where(Sheet.id == 1), Sheet.tags.set(("b", "b"))))

    stored = _stored_members(profile_run, "document")
    assert stored["futureKey"] == [1, "x"]
    assert (stored["tags"], stored["counts"]) == (["b", "b"], [1])


@pytest.mark.parametrize("layout", _LAYOUTS)
def test_a_stream_publishes_the_same_tuples_as_an_eager_read(
    profile_run: Any, layout: Layout
) -> None:
    db = _served(profile_run)
    entity = _ENTITIES[layout]
    db.transact(
        lambda tx: [
            tx.insert(
                entity(id=key, tags=tuple(f"t{key}" for _ in range(key)), lines=_NESTED_LINES)
            )
            for key in range(1, 5)
        ]
    )
    query = entity.where(entity.id >= 1).order_by(entity.id.asc())

    with db.stream(query, batch_size=2) as streamed:
        streamed_tags = [(row.tags, row.lines) for row in streamed]

    eager = [(row.tags, row.lines) for row in db.find(query).results()]
    assert (
        streamed_tags
        == eager
        == [(tuple(f"t{key}" for _ in range(key)), _NESTED_LINES) for key in range(1, 5)]
    )
